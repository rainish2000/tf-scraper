import hcl2
import csv
import os
import glob
import re

def parse_terraform_file(file_path):
    with open(file_path, 'r') as file:
        return hcl2.load(file)

def get_variable_value(var_name, variables, tfvars_files, root_variables, root_main_tf):
    if var_name in variables:
        return variables[var_name]

    for tfvars_file in tfvars_files:
        with open(tfvars_file, 'r') as file:
            tfvars = hcl2.load(file)
            if var_name in tfvars:
                return tfvars[var_name]

    if var_name in root_variables:
        return resolve_interpolation(root_variables[var_name], variables, tfvars_files, root_variables, root_main_tf)

    if var_name in root_main_tf:
        return resolve_interpolation(root_main_tf[var_name], variables, tfvars_files, root_variables, root_main_tf)

    return 'N/A'

def parse_variables(base_path):
    variables = {}
    variables_file = os.path.join(base_path, 'variables.tf')
    
    if os.path.exists(variables_file):
        with open(variables_file, 'r') as file:
            config = hcl2.load(file)
            for var in config.get('variable', []):
                for var_name, var_attrs in var.items():
                    if 'default' in var_attrs:
                        variables[var_name] = var_attrs['default']

    tfvars_files = glob.glob(os.path.join(base_path, '*.tfvars'))
    return variables, tfvars_files

def resolve_interpolation(value, variables, tfvars_files, root_variables, root_main_tf):
    if isinstance(value, str):
        matches = re.findall(r'\${var\.([a-zA-Z_][a-zA-Z0-9_]*)}', value)
        for match in matches:
            var_value = get_variable_value(match, variables, tfvars_files, root_variables, root_main_tf)
            value = value.replace(f'${{var.{match}}}', str(var_value))
    return value

def format_resource_type(resource_type):
    acronyms = ['aws', 'iam', 'kms', 'dns', 'cname', 'lb', 'ecr', 'ecs', 'vpc', 'db', 'eip', 'nat', 'acm']
    parts = resource_type.split('_')
    formatted_parts = [
        part.upper() if part.lower() in acronyms else part.capitalize()
        for part in parts
    ]
    formatted_resource_type = ' '.join(formatted_parts)
    return formatted_resource_type.replace('Appautoscaling', 'AppAutoScaling')

def get_resource_info(resource_type, resource_name, instances, variables, tfvars_files, root_variables, root_main_tf):
    resource_info = {
        'resource type': format_resource_type(resource_type),
        'resource name': '' if resource_name == 'this' else resource_name  # Keep underscores in resource name unless it is "this"
    }

    if resource_type in ['aws_instance', 'aws_db_instance']:
        instance_type = instances[resource_name].get('instance_type' if resource_type == 'aws_instance' else 'instance_class', 'N/A')
        instance_type = resolve_interpolation(instance_type, variables, tfvars_files, root_variables, root_main_tf)
        resource_info['instance type'] = instance_type

    if resource_type == 'aws_ecs_task_definition':
        cpu = instances[resource_name].get('cpu', 'N/A')
        memory = instances[resource_name].get('memory', 'N/A')
        resource_info['cpu'] = resolve_interpolation(cpu, variables, tfvars_files, root_variables, root_main_tf)
        resource_info['memory'] = resolve_interpolation(memory, variables, tfvars_files, root_variables, root_main_tf)

    if resource_type == 'aws_db_instance':
        storage_size = instances[resource_name].get('allocated_storage', 'N/A')
        resource_info['storage size'] = resolve_interpolation(storage_size, variables, tfvars_files, root_variables, root_main_tf)

    return resource_info

def get_root_variables_and_main_tf(root_path):
    root_variables = {}
    root_main_tf = {}
    root_variables_file = os.path.join(root_path, 'variables.tf')

    if os.path.exists(root_variables_file):
        with open(root_variables_file, 'r') as file:
            config = hcl2.load(file)
            for var in config.get('variable', []):
                for var_name, var_attrs in var.items():
                    if 'default' in var_attrs:
                        root_variables[var_name] = var_attrs['default']

    root_tfvars_files = glob.glob(os.path.join(root_path, '*.tfvars'))
    for tfvars_file in root_tfvars_files:
        with open(tfvars_file, 'r') as file:
            tfvars = hcl2.load(file)
            root_variables.update(tfvars)
    
    root_main_tf_file = os.path.join(root_path, 'main.tf')
    if os.path.exists(root_main_tf_file):
        with open(root_main_tf_file, 'r') as file:
            config = hcl2.load(file)
            for module in config.get('module', []):
                for module_name, module_attrs in module.items():
                    for attr_name, attr_value in module_attrs.items():
                        root_main_tf[attr_name] = attr_value

    return root_variables, root_main_tf

def get_resources(terraform_files, root_variables, root_main_tf):
    resources = []
    for file_path in terraform_files:
        dir_path = os.path.dirname(file_path)
        variables, tfvars_files = parse_variables(dir_path)
        try:
            terraform_config = parse_terraform_file(file_path)
            for resource in terraform_config.get('resource', []):
                for resource_type, instances in resource.items():
                    for instance_name in instances.keys():
                        resource_info = get_resource_info(resource_type, instance_name, instances, variables, tfvars_files, root_variables, root_main_tf)
                        resources.append(resource_info)
        except Exception as e:
            print(f"Error parsing {file_path}: {e}")
    return resources

def find_terraform_files(base_path):
    return glob.glob(os.path.join(base_path, '**', '*.tf'), recursive=True)

def write_to_csv(resources, output_file):
    fieldnames = ['resource type', 'resource name', 'cpu', 'memory', 'instance type', 'storage size']
    with open(output_file, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for resource in resources:
            writer.writerow(resource)

def main():
    base_path = '.'  # Current directory where the script is located
    output_csv_path = 'resources.csv'
    
    terraform_files = find_terraform_files(base_path)
    root_variables, root_main_tf = get_root_variables_and_main_tf(base_path)
    resources = get_resources(terraform_files, root_variables, root_main_tf)
    write_to_csv(resources, output_csv_path)

if __name__ == "__main__":
    main()
