#!/usr/bin/python3
"""Copyright 2020-2021 Advanced Micro Devices, Inc.
Manage build and installation"""

import re
import sys
import os
import platform
import subprocess
import argparse
import pathlib
from fnmatch import fnmatchcase

args = {}
param = {}
OS_info = {}

def parse_args():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(description="""Checks build arguments""")
    # common
    parser.add_argument('-g', '--debug', required=False, default = False,  action='store_true',
                        help='Generate Debug build (optional, default: False)')
    parser.add_argument(      '--build_dir', type=str, required=False, default = "build",
                        help='Build directory path (optional, default: build)')
    # parser.add_argument('-i', '--install', required=False, default = False, dest='install', action='store_true',
    #                     help='Install after build (optional, default: False)')
    parser.add_argument(      '--cmake_darg', required=False, dest='cmake_dargs', action='append', default=[],
                        help='List of additional cmake defines for builds (optional, e.g. CMAKE)')
    parser.add_argument('-v', '--verbose', required=False, default = False, action='store_true',
                        help='Verbose build (optional, default: False)')
    # rocblas-Examples
    parser.add_argument(     '--library_path', type=str, required=False, default = "", 
                        help='If non-standard path to the pre-built rocBLAS library (optional, default: C:\hipSDK)')
    return parser.parse_args()

def os_detect():
    global OS_info
    if os.name == "nt":
        OS_info["ID"] = platform.system()
    else:
        inf_file = "/etc/os-release"
        if os.path.exists(inf_file):
            with open(inf_file) as f:
                for line in f:
                    if "=" in line:
                        k,v = line.strip().split("=")
                        OS_info[k] = v.replace('"','')
    OS_info["NUM_PROC"] = os.cpu_count()
    print(OS_info)

def create_dir(dir_path):
    full_path = ""
    if os.path.isabs(dir_path):
        full_path = dir_path
    else:
        full_path = os.path.join( os.getcwd(), dir_path )
    pathlib.Path(full_path).mkdir(parents=True, exist_ok=True)
    return

def delete_dir(dir_path) :
    if (not os.path.exists(dir_path)):
        return
    if os.name == "nt":
        run_cmd( "RMDIR" , f"/S /Q {dir_path}")
    else:
        run_cmd( "rm" , f"-rf {dir_path}")

def cmake_path(os_path):
    if os.name == "nt":
        return os_path.replace("\\", "/")
    else:
        return os_path
    
def config_cmd(src_path, use_hipcc):
    global args
    global OS_info
    cmake_executable = ""
    cmake_options = []

    cmake_platform_opts = []
    if os.name == "nt":
        sdk_path = os.getenv( 'ROCM_CMAKE_PATH', "C:/hipSDK")
        cmake_executable = "cmake"
        #set CPACK_PACKAGING_INSTALL_PREFIX= defined as blank as it is appended to end of path for archive creation
        #cmake_platform_opts.append( f"-DCPACK_PACKAGING_INSTALL_PREFIX=" )
        #cmake_platform_opts.append( f"-DCMAKE_INSTALL_PREFIX=\"C:/hipSDK\"" )
        if use_hipcc:
            generator = f"-G Ninja"
            cmake_options.append( generator )
    else:
        sdk_path = os.getenv( 'ROCM_PATH', "/opt/rocm")
        if (OS_info["ID"] in ['centos', 'rhel']):
          cmake_executable = "cmake" # was cmake3 but now we built cmake
        else:
          cmake_executable = "cmake"
        cmake_platform_opts.append( f"-DROCM_DIR:PATH={sdk_path} -DCPACK_PACKAGING_INSTALL_PREFIX={sdk_path}" )
        cmake_platform_opts.append( f"-DCMAKE_INSTALL_PREFIX=\"rocblas-install\"" )
        toolchain = "toolchain-linux.cmake"

    print( f"Build source path: {src_path}")

    if use_hipcc:
        cmake_options.append( f"-DCMAKE_CXX_COMPILER=hipcc.bat" )

    cmake_options.extend( cmake_platform_opts )

    if args.library_path:
        prefix_path = cmake_path(args.library_path)
    elif os.path.exists(sdk_path):
        prefix_path = sdk_path

    if prefix_path:
        cmake_base_options = f"-DCMAKE_PREFIX_PATH:PATH={prefix_path}" 
        cmake_options.append( cmake_base_options )

    # packaging options
    # cmake_pack_options = f"-DCPACK_SET_DESTDIR=OFF" 
    # cmake_options.append( cmake_pack_options )

    if os.getenv('CMAKE_CXX_COMPILER_LAUNCHER'):
        cmake_options.append( f"-DCMAKE_CXX_COMPILER_LAUNCHER={os.getenv('CMAKE_CXX_COMPILER_LAUNCHER')}" )

    print( cmake_options )


    build_dir = os.path.abspath(args.build_dir)
    # build type
    if use_hipcc:
        cmake_config = ""
        if not args.debug:
            build_path = os.path.join(build_dir, "release")
            cmake_config="Release"
        else:
            build_path = os.path.join(build_dir, "debug")
            cmake_config="Debug"

        cmake_options.append( f"-DCMAKE_BUILD_TYPE={cmake_config}" ) 
    else:
        build_path = os.path.join(build_dir, "msvc")

    # clean
    delete_dir( build_path )
    create_dir( build_path )
    os.chdir( build_path )

    if args.cmake_dargs:
        for i in args.cmake_dargs:
          cmake_options.append( f"-D{i}" )

    cmake_options.append( f"{src_path}")
    cmd_opts = " ".join(cmake_options)

    return cmake_executable, cmd_opts


def make_cmd():
    global args
    global OS_info

    make_options = []

    nproc = OS_info["NUM_PROC"]
    if os.name == "nt":
        make_executable = f"cmake.exe --build . " # ninja
        if args.verbose:
          make_options.append( "--verbose" )
        make_options.append( "--target all" )
        # if args.install:
        #   make_options.append( "--target package --target install" )
    else:
        make_executable = f"make -j{nproc}"
        if args.verbose:
          make_options.append( "VERBOSE=1" )
        if True: # args.install:
         make_options.append( "install" )
    cmd_opts = " ".join(make_options)

    return make_executable, cmd_opts


def msvc_cmd():
    global args
    global OS_info

    make_options = []

    nproc = OS_info["NUM_PROC"]
    if os.name == "nt":
        make_executable = f"msbuild rocblas-examples.sln -property:Configuration=Release" 
        if args.verbose:
          make_options.append( "--verbose" )
    else:
        make_executable = f"make -j{nproc}"
        if args.verbose:
          make_options.append( "VERBOSE=1" )
        if True: # args.install:
         make_options.append( "install" )
    cmd_opts = " ".join(make_options)

    return make_executable, cmd_opts



def run_cmd(exe, opts):
    program = f"{exe} {opts}"
    print(program)
    proc = subprocess.run(program, check=True, stderr=subprocess.STDOUT, shell=True)
    return proc.returncode

def main():
    global args
    os_detect()
    args = parse_args()

    cwd = os.getcwd()
    src_path = cmake_path(cwd)

    # configure for non hipcc
    exe, opts = config_cmd(src_path, False)
    run_cmd(exe, opts)

    # make
    exe, opts = msvc_cmd()
    run_cmd(exe, opts)

    # second pass with hipcc and ninja on windows
    os.chdir(cwd)

    # configure for hipcc
    exe, opts = config_cmd(src_path, True)
    run_cmd(exe, opts)

    # make 
    exe, opts = make_cmd()
    run_cmd(exe, opts)

if __name__ == '__main__':
    main()

