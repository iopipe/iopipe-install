#!/usr/bin/env python3
from . import update

import boto3
import botocore
import click
import os
import shutil

IOPIPE_FF_CLOUDFORMATION = os.environ.get('IOPIPE_FF_CLOUDFORMATION')


@click.group()
def cli():
    None

@click.group()
def stack():
    None

@click.group(name="lambda")
def lambda_group():
    None

#@click.group()
#def sam():
#    None
#cli.add_command(sam)
#
#@click.group()
#def gosls():
#    None
#cli.add_command(gosls)

@click.command(name="template")
@click.option("--input", "-i", default='template.json', help="Cloudformation JSON file.")
@click.option("--function", "-f", required=True, help="Lambda Function name")
@click.option("--output", "-o", default='-', help="Output file for modified template.")
@click.option("--token", "-t", envvar="IOPIPE_TOKEN", required=True, help="IOpipe Token")
def cf_update_template(template, function, output, token):
    update.update_cloudformation_file(template, function, output, token)

@click.command(name="update")
@click.option("--stack-id", "-s", required=True, help="Cloudformation Stack ID.")
@click.option("--function", "-f", required=True, help="Lambda Function name")
@click.option("--token", "-t", envvar="IOPIPE_TOKEN", required=True, help="IOpipe Token")
def cf_update_stack(stack_id, function, token):
    update.update_cloudformation_stack(stack_id, function, token)

@click.command(name="install")
@click.option("--function", "-f", required=True, help="Lambda Function name")
@click.option("--layer-arn", "-l", help="Layer ARN for IOpipe library (default: auto-detect)")
@click.option("--token", "-t", envvar="IOPIPE_TOKEN", required=True, help="IOpipe Token")
def api_install(function, layer_arn, token):
    try:
        update.apply_function_api(function, layer_arn, token)
    except update.MultipleLayersException:
        print ("Multiple layers found. Pass --layer-arn to specify layer ARN")
        None

@click.command(name="uninstall")
@click.option("--function", "-f", required=True, help="Lambda Function name")
@click.option("--layer-arn", "-l", help="Layer ARN for IOpipe library (default: auto-detect)")
def api_uninstall(function, layer_arn):
    update.remove_function_api(function, layer_arn)

@click.command(name="list")
@click.option("--quiet", "-q", help="Skip headers", is_flag=True)
@click.option("--filter", "-f", help="Apply a filter to the list.", type=click.Choice(['all', 'installed', 'not-installed']))
def lambda_list_functions(quiet, filter):
    # this use of `filter` worries me as it's a keyword,
    # but it actually works? Clickly doesn't give
    # us enough control here to change the variable name? -Erica
    buffer = []
    _, consrows = shutil.get_terminal_size((80,50))
    for idx, line in enumerate(list_functions(quiet, filter)):
        buffer.append(line)

        # If we've buffered as many lines as the height of the console,
        # then start a pager and empty the buffer.
        if idx > 0 and idx % consrows == 0:
            click.echo_via_pager(iter(buffer))
            buffer = []
    # Print all lines on the last page.
    for line in buffer:
        click.echo(line)

def list_functions(quiet, filter_choice):
    coltmpl = "{:<64}\t{:<12}\t{:>12}"
    conscols, consrows = shutil.get_terminal_size((80,50))
    # set all if the filter_choice is "all" or there is no filter_choice active.
    all = filter_choice == "all" or not filter_choice

    if not quiet:
        yield coltmpl.format("Function Name", "Runtime", "Installed")
        # ascii table limbo line ---
        yield ("{:-^%s}" % (str(conscols),)).format("")

    AwsLambda = boto3.client('lambda')
    next_marker = None
    while True:
        list_func_args = {'MaxItems': consrows}
        if next_marker:
            list_func_args = {'Marker': next_marker, 'MaxItems': consrows}
        func_resp = AwsLambda.list_functions(**list_func_args)
        next_marker = func_resp.get("NextMarker", None)
        funcs = func_resp.get("Functions", [])

        for f in funcs:
            runtime = f.get("Runtime")
            new_handler = update.RUNTIME_CONFIG.get(runtime, {}).get('Handler', None)
            if f.get("Handler") == new_handler:
                f["-x-iopipe-enabled"] = True
                if not all and filter_choice != "installed":
                    continue
            elif not all and filter_choice == "installed":
                continue
            yield coltmpl.format(f.get("FunctionName"), f.get("Runtime"), f.get("-x-iopipe-enabled", False))

        if not next_marker:
            break

def click_groups():
    if IOPIPE_FF_CLOUDFORMATION:
        cli.add_command(stack)
        stack.add_command(cf_update_template)
        stack.add_command(cf_update_stack)

    cli.add_command(lambda_group)
    lambda_group.add_command(lambda_list_functions)
    lambda_group.add_command(api_install)
    lambda_group.add_command(api_uninstall)

def main():
    click_groups()
    try:
        cli()
    except botocore.exceptions.NoRegionError:
        print("You must specify a region. Have you run `aws configure`?")
    except botocore.exceptions.NoCredentialsError:
        print("No AWS credentials configured. Have you run `aws configure`?")
