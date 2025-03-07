import json
import os
import yaml
import copy

from bincrafters.build_shared import get_bool_from_env, get_conan_vars, get_recipe_path, get_version_from_ci
from bincrafters.autodetect import *
from bincrafters.utils import *
from bincrafters.check_compatibility import *
import bincrafters


def _is_gha_existing():
    if utils_file_contains(os.path.join(".github", "workflows", "conan.yml"), "bincrafters-package-tools") \
            and utils_file_contains(os.path.join(".github", "workflows", "conan.yml"), "bincrafters_package_tools"):
        return True

    return False


def _run_macos_jobs_on_gha():
    if utils_file_contains("azure-pipelines.yml", "name: bincrafters/templates") \
            and utils_file_contains("azure-pipelines.yml", "template: .ci/azure.yml@templates"):
        return False

    return True


def _run_windows_jobs_on_gha():
    if utils_file_contains("azure-pipelines.yml", "name: bincrafters/templates") \
            and utils_file_contains("azure-pipelines.yml", "template: .ci/azure.yml@templates"):
        return False

    if utils_file_contains("appveyor.yml", "pip install bincrafters_package_tools"):
        return False

    return True


def _do_discard_duplicated_build_ids() -> bool:
    return get_bool_from_env("BPT_MATRIX_DISCARD_DUPLICATE_BUILD_IDS", default="true")

_configs = {
    "ubuntu-gcc-5": {"name": "GCC 5", "compiler": "GCC", "version": "5", "os": "ubuntu-latest", "dockerImage": "teeks99/gcc-ubuntu:5"},
    "ubuntu-gcc-6": {"name": "GCC 6", "compiler": "GCC", "version": "6", "os": "ubuntu-latest", "dockerImage": "teeks99/gcc-ubuntu:6"},
    "ubuntu-gcc-7": {"name": "GCC 7", "compiler": "GCC", "version": "7", "os": "ubuntu-latest", "dockerImage": "teeks99/gcc-ubuntu:7"},
    "ubuntu-gcc-8": {"name": "GCC 8", "compiler": "GCC", "version": "8", "os": "ubuntu-latest", "dockerImage": "teeks99/gcc-ubuntu:8"},
    "ubuntu-gcc-9": {"name": "GCC 9", "compiler": "GCC", "version": "9", "os": "ubuntu-latest", "dockerImage": "teeks99/gcc-ubuntu:9"},
    "ubuntu-gcc-10": {"name": "GCC 10", "compiler": "GCC", "version": "10", "os": "ubuntu-latest", "dockerImage": "teeks99/gcc-ubuntu:10"},
    "ubuntu-gcc-11": {"name": "GCC 11", "compiler": "GCC", "version": "11", "os": "ubuntu-latest", "dockerImage": "teeks99/gcc-ubuntu:11"},
    "ubuntu-gcc-12": {"name": "GCC 12", "compiler": "GCC", "version": "12", "os": "ubuntu-latest", "dockerImage": "teeks99/gcc-ubuntu:12_20221001_1312"},
    "ubuntu-clang-7": {"name": "CLANG 7", "compiler": "CLANG", "version": "7", "os": "ubuntu-latest", "dockerImage": "teeks99/clang-ubuntu:7"},
    "ubuntu-clang-8": {"name": "CLANG 8", "compiler": "CLANG", "version": "8", "os": "ubuntu-latest", "dockerImage": "teeks99/clang-ubuntu:8"},
    "ubuntu-clang-9": {"name": "CLANG 9", "compiler": "CLANG", "version": "9", "os": "ubuntu-latest", "dockerImage": "teeks99/clang-ubuntu:9"},
    "ubuntu-clang-10": {"name": "CLANG 10", "compiler": "CLANG", "version": "10", "os": "ubuntu-latest", "dockerImage": "teeks99/clang-ubuntu:10"},
    "ubuntu-clang-11": {"name": "CLANG 11", "compiler": "CLANG", "version": "11", "os": "ubuntu-latest", "dockerImage": "teeks99/clang-ubuntu:11"},
    "ubuntu-clang-12": {"name": "CLANG 12", "compiler": "CLANG", "version": "12", "os": "ubuntu-latest", "dockerImage": "teeks99/clang-ubuntu:12"},
    "ubuntu-clang-13": {"name": "CLANG 13", "compiler": "CLANG", "version": "13", "os": "ubuntu-latest", "dockerImage": "teeks99/clang-ubuntu:13"},
    "ubuntu-clang-14": {"name": "CLANG 14", "compiler": "CLANG", "version": "14", "os": "ubuntu-latest", "dockerImage": "teeks99/clang-ubuntu:14"},
    "ubuntu-clang-15": {"name": "CLANG 15", "compiler": "CLANG", "version": "15", "os": "ubuntu-latest", "dockerImage": "teeks99/clang-ubuntu:15"},
    "ubuntu-clang-16": {"name": "CLANG 16", "compiler": "CLANG", "version": "16", "os": "ubuntu-latest", "dockerImage": "teeks99/clang-ubuntu:16_20221004_0023"},
    "macos-xcode-11": {"name": "macOS Apple-Clang 11", "compiler": "APPLE_CLANG", "version": "11.7", "os": "macOS-latest"},
    "macos-xcode-12": {"name": "macOS Apple-Clang 12", "compiler": "APPLE_CLANG", "version": "12.5.1", "os": "macOS-latest"},
    "macos-xcode-13": {"name": "macOS Apple-Clang 13", "compiler": "APPLE_CLANG", "version": "13.2.1", "os": "macOS-latest"},
    "macos-xcode-14": {"name": "macOS Apple-Clang 14", "compiler": "APPLE_CLANG", "version": "14.0.1", "os": "macOS-12"},
    "win-vs-2019": {"name": "Windows VS 2019", "compiler": "VISUAL", "version": "16", "os": "windows-2019"},
    "win-vs-2022": {"name": "Windows VS 2022", "compiler": "VISUAL", "version": "17", "os": "windows-2022"},
}

def _get_configs(*configs):
    result = []
    for config in configs:
        result.append(_configs[config])
    return result

def _get_base_config(recipe_directory: str, platform: str, split_by_build_types: bool, build_set: str = "full", recipe_type: str = ""):
    if recipe_type == "":
        if _do_discard_duplicated_build_ids():
            cwd = os.getcwd()
            os.chdir(recipe_directory)
            recipe_type = autodetect()
            os.chdir(cwd)
        else:
            # Useful for installer_only / header_only recipes that still want the full build matrix
            # Eventually replace with an actual dynamic matrix generation
            recipe_type = "recipe_manual_full_matrix"

    matrix = {}
    matrix_minimal = {}

    if platform == "gha":
        run_macos = _run_macos_jobs_on_gha()
        run_windows = _run_windows_jobs_on_gha()
        if recipe_type == "installer":
            matrix["config"] = _get_configs("ubuntu-gcc-11", "win-xcode-13", "win-vs-2022")
            matrix_minimal["config"] = matrix["config"].copy()
        elif recipe_type == "unconditional_header_only":
            matrix["config"] = _get_configs("ubuntu-clang-12", "win-vs-2022")
            matrix_minimal["config"] = matrix["config"].copy()
        else:
            matrix["config"] = _get_configs(
                # "ubuntu-gcc-5", "ubuntu-gcc-6", "ubuntu-gcc-7",
                "ubuntu-gcc-8", "ubuntu-gcc-9", "ubuntu-gcc-10",
                "ubuntu-gcc-11", "ubuntu-gcc-12",
                "ubuntu-clang-7", "ubuntu-clang-8", "ubuntu-clang-9",
                "ubuntu-clang-10", "ubuntu-clang-11", "ubuntu-clang-12",
                "ubuntu-clang-13", "ubuntu-clang-14", "ubuntu-clang-15",
                "ubuntu-clang-16")
            matrix_minimal["config"] = _get_configs("ubuntu-gcc-12", "ubuntu-clang-16")
            if run_macos:
                matrix["config"] += _get_configs(
                    "macos-xcode-11", "macos-xcode-12", "macos-xcode-13", "macos-xcode-14")
                matrix_minimal["config"] += _get_configs("macos-xcode-14")
            if run_windows:
                matrix["config"] += _get_configs("win-vs-2019", "win-vs-2022")
                matrix_minimal["config"] += _get_configs("win-vs-2022")
    elif platform == "azp":
        if _is_gha_existing() and recipe_type in ["installer", "unconditional_header_only", "recipe_manual_full_matrix"]:
            matrix["config"] = []
            matrix_minimal["config"] = []
        else:
            matrix["config"] = [
                {"name": "macOS Apple-Clang 10", "compiler": "APPLE_CLANG", "version": "10.0", "os": "macOS-10.15"},
                {"name": "macOS Apple-Clang 11", "compiler": "APPLE_CLANG", "version": "11.0", "os": "macOS-10.15"},
                {"name": "macOS Apple-Clang 12", "compiler": "APPLE_CLANG", "version": "12.0", "os": "macOS-10.15"},
                {"name": "Windows VS 2017", "compiler": "VISUAL", "version": "15", "os": "vs2017-win2016"},
                {"name": "Windows VS 2019", "compiler": "VISUAL", "version": "16", "os": "windows-2019"},
                {"name": "Windows VS 2022", "compiler": "VISUAL", "version": "17", "os": "windows-2022"},
            ]
            matrix_minimal["config"] = [
                {"name": "macOS Apple-Clang 11", "compiler": "APPLE_CLANG", "version": "11.0", "os": "macOS-10.15"},
                {"name": "Windows VS 2019", "compiler": "VISUAL", "version": "16", "os": "windows-2019"},
            ]

    # Split build jobs by build_type (Debug, Release)
    # Duplicate each builds job, then add the buildType value
    if split_by_build_types is None:
        # env var BPT_MATRIX_SPLIT_BY_BUILD_TYPES should be preferred
        # over BPT_SPLIT_BY_BUILD_TYPES and splitByBuildTypes (deprecated)
        split_by_build_types = get_bool_from_env("BPT_MATRIX_SPLIT_BY_BUILD_TYPES",
                                                 get_bool_from_env("BPT_SPLIT_BY_BUILD_TYPES",
                                                                   get_bool_from_env("splitByBuildTypes", False)))

    if split_by_build_types:
        matrix_tmp = copy.deepcopy(matrix)
        matrix_minimal_tmp = copy.deepcopy(matrix_minimal)

        for m_tmp, m in [[matrix_tmp, matrix], [matrix_minimal_tmp, matrix_minimal]]:
            for i, config_set in enumerate(m_tmp["config"], start=0):
                m["config"].insert((i * 2) + 1, config_set.copy())
            for config_set in m["config"][0::2]:
                config_set["name"] = "{} Release".format(config_set["name"])
                config_set["buildType"] = "Release"
            for config_set in m["config"][1::2]:
                config_set["name"] = "{} Debug".format(config_set["name"])
                config_set["buildType"] = "Debug"

    if build_set == "full":
        return matrix
    elif build_set == "minimal":
        return matrix_minimal
    else:
        return {"config": []}


def generate_ci_jobs(platform: str, recipe_type: str = autodetect(), split_by_build_types: bool = False) -> str:
    if platform != "gha" and platform != "azp":
        return ""

    if not is_ci_config_compatible(platform=platform, feature="generate-ci-jobs"):
        raise Exception(
            "bincrafters-package-tools {} requires a newer {} CI config file; minimum version {} - current version {}".format(
                bincrafters.__version__,
                platform,
                get_minimum_compatible_version(platform=platform, feature="generate-ci-jobs"),
                get_config_file_version()
            ))

    directory_structure = autodetect_directory_structure()
    final_matrix = {"config": []}

    def _detect_changed_directories(path_filter: str = None) -> set:
        changed_dirs = []
        current_commit = utils_git_get_current_commit()
        current_branch = utils_git_get_current_branch()
        default_branch = utils_git_get_default_branch()

        changed_dirs.extend(utils_git_get_changed_dirs(base=current_commit))

        if default_branch != current_branch:
            # The default branch might not be tracked locally
            # i.e. "main" might be unknown, while "origin/main" should always be known
            # similar for the current_branch, so lets use the hash commit which should be always be known
            changed_dirs.extend(utils_git_get_changed_dirs(base="origin/{}".format(default_branch), head=current_commit))

        if path_filter:
            # Only list directories which start with a certain path
            # It also removes this filter prefix from the path
            # e.g. only get changed directories in recipes/ and remove recipes/ from results
            changed_dirs = [x.replace(path_filter, "") for x in changed_dirs if path_filter in x]

        # Remove trailing /
        changed_dirs = [os.path.dirname(x) for x in changed_dirs]

        return set(changed_dirs)

    def _parse_recipe_directory(path: str, path_filter: str = None, recipe_displayname: str = None):
        changed_dirs = _detect_changed_directories(path_filter=path_filter)
        config_file = os.path.join(path, "config.yml")
        config_yml = yaml.load(open(config_file, "r"), yaml.Loader)
        for version, version_attr in config_yml["versions"].items():
            version_build_value = version_attr.get("build", "full")
            # If we are on a branch like testing/3.0.0 then only build 3.0.0
            # regardless of config.yml settings
            # If we are on an unversioned branch, only build versions which dirs got changed
            if (get_version_from_ci() == "" and version_attr["folder"] in changed_dirs) \
                    or get_version_from_ci() == version:
                if version_build_value != "none":
                    if version_build_value == "full" or version_build_value == "minimal":
                        working_matrix = _get_base_config(
                            recipe_directory=os.path.join(path, version_attr["folder"]),
                            platform=platform,
                            split_by_build_types=split_by_build_types,
                            build_set=version_build_value
                        )
                    else:
                        raise ValueError("Unknown build value for version {} detected!".format(version))

                    for build_config in working_matrix["config"]:
                        new_config = build_config.copy()
                        if not path_filter:
                            new_config["cwd"] = version_attr["folder"]
                            new_config["name"] = "{} {}".format(version, new_config["name"])
                        else:
                            new_config["cwd"] = "{}{}".format(path_filter, version_attr["folder"])
                            new_config["name"] = "{}/{} {}".format(recipe_displayname, version, new_config["name"])
                        new_config["recipe_version"] = version
                        final_matrix["config"].append(new_config)

    def _parse_standalone_recipe(path: str, path_filter: str = None, recipe_displayname: str = None):
        data_file = os.path.join(path, "conandata.yml")
        data_yml = yaml.load(open(data_file, "r"), yaml.Loader)
        for version, _ in data_yml["sources"].items():
            working_matrix = _get_base_config(
                recipe_directory=path,
                platform=platform,
                split_by_build_types=split_by_build_types,
                build_set="full"
            )
            for build_config in working_matrix["config"]:
                new_config = build_config.copy()
                new_config["cwd"] = path.replace(os.getcwd(), "")
                new_config["name"] = "{} {}".format(version, new_config["name"])
                new_config["recipe_version"] = version
                final_matrix["config"].append(new_config)

    if directory_structure == DIR_STRUCTURE_ONE_RECIPE_ONE_VERSION:
        matrix = _get_base_config(recipe_directory=".", platform=platform, split_by_build_types=split_by_build_types)
        for build_config in matrix["config"]:
            new_config = build_config.copy()
            new_config["cwd"] = "./"
            _, fixed_version, _ = get_conan_vars(recipe=get_recipe_path())
            new_config["recipe_version"] = fixed_version
            final_matrix["config"].append(new_config)

    elif directory_structure == DIR_STRUCTURE_ONE_RECIPE_MANY_VERSIONS:
        _parse_recipe_directory(path=os.getcwd())

    elif directory_structure == DIR_STRUCTURE_CCI:
        recipes = [f.path for f in os.scandir("recipes") if f.is_dir()]
        for recipe_folder in recipes:
            # the path_filter should end with a / so that the results don't start with one
            recipe_displayname = recipe_folder.replace("recipes/", "")
            _parse_recipe_directory(path=recipe_folder,
                                    path_filter="{}/".format(recipe_folder),
                                    recipe_displayname=recipe_displayname)

    elif directory_structure == DIR_STRUCTURE_STANDALONE_RECIPE_MANY_VERSIONS:
        _parse_standalone_recipe(os.getcwd())

    # Now where we have the complete matrix, we have to parse it in a final string
    # which can be understood by the target platform
    matrix_string = "{}"

    if platform == "gha":
        matrix_string = json.dumps(final_matrix)
    elif platform == "azp":
        platform_matrix = {}
        for build_config in final_matrix["config"]:
            platform_matrix[build_config["name"]] = build_config
        matrix_string = json.dumps(platform_matrix)

    return matrix_string
