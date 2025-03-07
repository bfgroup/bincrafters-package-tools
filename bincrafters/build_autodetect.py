import sys
import subprocess
import tempfile
import os

from bincrafters.build_shared import printer, get_os
from bincrafters import build_shared
from bincrafters.autodetect import *


def _flush_output():
    sys.stderr.flush()
    sys.stdout.flush()


def _get_default_builder(shared_option_name=None,
                    pure_c=True,
                    dll_with_static_runtime=False,
                    build_policy=None,
                    cwd=None,
                    reference=None,
                    **kwargs):
    recipe = build_shared.get_recipe_path(cwd)

    builder = build_shared.get_builder(build_policy, cwd=cwd, **kwargs)
    if shared_option_name is None and build_shared.is_shared():
        shared_option_name = "%s:shared" % build_shared.get_name_from_recipe(recipe=recipe)

    builder.add_common_builds(
        shared_option_name=shared_option_name,
        pure_c=pure_c,
        dll_with_static_runtime=dll_with_static_runtime,
        reference=reference)

    return builder


def _get_builder():
    ###
    # Output collected recipe information in the builds logs
    ###
    recipe_conanfile = get_recipe_path()
    printer.print_message("Recipe path: {}".format(str(recipe_conanfile)))

    recipe_is_installer = is_installer()
    printer.print_message("Is the package an installer for executable(s)? {}"
                          .format(str(recipe_is_installer)))

    if not recipe_is_installer:
        recipe_is_unconditional_header_only = is_unconditional_header_only()
        printer.print_message("Is the package header only? {}"
                              .format(str(recipe_is_unconditional_header_only)))

        recipe_is_testable_header_only = is_testable_header_only()
        printer.print_message("Is the package testable header only? {}"
                              .format(str(recipe_is_testable_header_only)))

        if not recipe_is_unconditional_header_only:
            recipe_is_conditional_header_only = is_conditional_header_only()
            printer.print_message("Is the package conditionally header only ('header_only' option)? {}"
                                  .format(str(recipe_is_conditional_header_only)))

            recipe_is_pure_c = is_pure_c()
            printer.print_message("Is the package C-only? {}".format(str(recipe_is_pure_c)))

    _flush_output()

    ###
    # Create builder
    ###
    kwargs = {}

    if autodetect_directory_structure() == DIR_STRUCTURE_ONE_RECIPE_MANY_VERSIONS \
            or autodetect_directory_structure() == DIR_STRUCTURE_CCI:
        kwargs["stable_branch_pattern"] = os.getenv("CONAN_STABLE_BRANCH_PATTERN", "main")

    if recipe_is_installer:
        arch = os.getenv("ARCH", "x86_64")
        builder = build_shared.get_builder(**kwargs)
        builder.add({"os": get_os(), "arch_build": arch, "arch": arch}, {}, {}, {})
    elif is_testable_header_only():
        builder = build_shared.get_builder(**kwargs)
        builder.add()
    elif recipe_is_unconditional_header_only:
        builder = build_shared.get_builder(**kwargs)
        builder.add()
    else:
        builder = _get_default_builder(pure_c=recipe_is_pure_c, **kwargs)

    return builder


def run_autodetect():
    ###
    # Enabling Conan download cache
    ###
    printer.print_message("Enabling Conan download cache ...")

    tmpdir = os.path.join(tempfile.gettempdir(), "conan")

    os.makedirs(tmpdir, mode=0o777)
    # In some cases Python may ignore the mode of makedirs, do it again explicitly with chmod
    os.chmod(tmpdir, mode=0o777)

    setup_sh = os.path.join(tmpdir, "setup.sh")
    with open(setup_sh, "w") as f:
        f.write("""
#!/bin/sh
conan config set storage.download_cache='{0}'
conan config set general.revisions_enabled=1
""".format(tmpdir))
    os.chmod(setup_sh, mode=0o777)

    os.system('conan config set storage.download_cache="{}"'.format(tmpdir))
    os.system('conan config set general.revisions_enabled=1')
    os.environ["CONAN_DOCKER_ENTRY_SCRIPT"] = "cat '{0}' && '{0}'".format(setup_sh)
    conan_docker_run_options = os.environ.get('CONAN_DOCKER_RUN_OPTIONS','')
    conan_docker_run_options += " -v '{}':'/tmp/conan'".format(tmpdir)
    os.environ['CONAN_DOCKER_RUN_OPTIONS'] = conan_docker_run_options
    os.environ['CONAN_PIP_USE_SUDO'] = "False"

    ###
    # Enabling installing system_requirements
    ###
    os.environ["CONAN_SYSREQUIRES_MODE"] = "enabled"
    os.environ["CONAN_GLOBAL_CONF"] = "tools.system.package_manager:mode=install"

    ###
    # Detect and execute custom build.py file if existing
    ###
    has_custom_build_py, custom_build_py_path = is_custom_build_py_existing()

    if has_custom_build_py:
        printer.print_message("Custom build.py detected. Executing ...")
        _flush_output()

        new_wd = os.path.dirname(custom_build_py_path)
        if new_wd == "":
            new_wd = ".{}".format(os.sep)

        # build.py files have no knowledge about the directory structure above them.
        # Delete the env variable or BPT is appending the path a second time
        # when build.py calls BPT
        if "BPT_CWD" in os.environ:
            del os.environ["BPT_CWD"]

        subprocess.run("python build.py", cwd=new_wd, shell=True, check=True)
        return

    ###
    # Start the build
    ###
    builder = _get_builder()
    builder.run()

