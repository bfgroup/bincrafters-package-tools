import json
import os
import subprocess
import sys


def _flush_output():
    sys.stderr.flush()
    sys.stdout.flush()


def prepare_env(platform: str, config: json, select_config: str = None):
    if platform != "gha" and platform != "azp":
        raise ValueError("Only GitHub Actions and Azure Pipelines is supported at this point.")

    if platform != "azp" and select_config is not None:
        raise ValueError("The --select-config parameter can only be used with Azure Pipelines.")

    if select_config:
        config = config[select_config]

    def _proc_run(args, check=False):
        print(">>", args)
        _flush_output()
        subprocess.run(args, shell=True, check=check)

    def _set_env_variable(var_name: str, value: str):
        print("{} = {}".format(var_name, value))
        os.environ[var_name] = value
        if platform == "gha":
            if compiler in ["VISUAL", "MSVC"]:
                os.system('echo {}={}>> {}'.format(var_name, value, os.getenv("GITHUB_ENV")))
            else:
                _proc_run(
                    'echo "{}={}" >> $GITHUB_ENV'.format(var_name, value))

        if platform == "azp":
            if compiler in ["VISUAL", "MSVC"]:
                _proc_run(
                    'echo ##vso[task.setvariable variable={}]{}'.format(var_name, value))
            else:
                _proc_run(
                    'echo "##vso[task.setvariable variable={}]{}"'.format(var_name, value))

    compiler = config["compiler"]
    compiler_version = config["version"]
    docker_image = config.get("dockerImage", "")
    build_type = config.get("buildType", "")

    _set_env_variable("BPT_CWD", config["cwd"])
    _set_env_variable("CONAN_VERSION", config["recipe_version"])
    _set_env_variable("CONAN_DOCKER_IMAGE_SKIP_PULL", "True")

    if compiler == "APPLE_CLANG":
        if "." not in compiler_version:
            compiler_version = "{}.0".format(compiler_version)

    _set_env_variable("CONAN_{}_VERSIONS".format(compiler), compiler_version)

    if compiler == "GCC" or compiler == "CLANG":
        if docker_image == "":
            compiler_lower = compiler.lower()
            version_without_dot = compiler_version.replace(".", "")
            if (compiler == "GCC" and float(compiler_version) >= 11) or \
                    (compiler == "CLANG" and float(compiler_version) >= 12):
                # Use "modern" CDT containers for newer compilers
                docker_image = "conanio/{}{}-ubuntu16.04".format(compiler_lower, version_without_dot)
            else:
                docker_image = "conanio/{}{}".format(compiler_lower, version_without_dot)
        _set_env_variable("CONAN_DOCKER_IMAGE", docker_image)

    if build_type != "":
        _set_env_variable("CONAN_BUILD_TYPES", build_type)

    if platform == "gha" or platform == "azp":
        if compiler == "APPLE_CLANG":
            xcode_mapping = {
                "9.1": "/Applications/Xcode_9.4.1.app",
                "10.0": "/Applications/Xcode_10.3.app",
                "11.0": "/Applications/Xcode_11.5.app",
                "12.0": "/Applications/Xcode_12.4.app",
            }
            if compiler_version in xcode_mapping:
                _proc_run(
                    'sudo xcode-select -switch "{}"'.format(xcode_mapping[compiler_version]))
                print('executing: xcode-select -switch "{}"'.format(xcode_mapping[compiler_version]))

            _proc_run(
                'clang++ --version')

        if compiler in ["VISUAL", "MSVC"]:
            with open(os.path.join(os.path.dirname(__file__), "prepare_env_azp_windows.ps1"), "r") as file:
                content = file.read()
                file.close()

            with open("execute.ps1", "w", encoding="utf-8") as file:
                file.write(content)
                file.close()

            _proc_run("pip install --upgrade cmake", check=True)
            _proc_run("powershell -file {}".format(os.path.join(os.getcwd(), "execute.ps1")), check=True)

    if platform == "gha" and (compiler == "GCC" or compiler == "CLANG"):
        _proc_run('docker system prune --all --force --volumes')
        _proc_run('sudo rm -rf "/usr/local/share/boost"')
        _proc_run('sudo rm -rf "$AGENT_TOOLSDIRECTORY/CodeQL"')
        _proc_run('sudo rm -rf "$AGENT_TOOLSDIRECTORY/Ruby"')
        _proc_run('sudo rm -rf "$AGENT_TOOLSDIRECTORY/boost"')
        _proc_run('sudo rm -rf "$AGENT_TOOLSDIRECTORY/go"')
        _proc_run('sudo rm -rf "$AGENT_TOOLSDIRECTORY/node"')
    
    def _docker_run(command):
        _proc_run('docker run {} "{}" /bin/sh -c "{}"'.format(
            "--name conan_runner",
            docker_image,
            command))
        _proc_run('docker commit conan_runner {}'.format(docker_image))
        _proc_run('docker stop conan_runner')
        _proc_run('docker rm conan_runner')
        _proc_run('docker ps')
        _proc_run('docker images')

    if platform == "gha" and len(docker_image) > 0:
        _proc_run('docker pull "{}"'.format(docker_image))
        _docker_run("apt install -y python3-pip")

    _proc_run("conan user")
