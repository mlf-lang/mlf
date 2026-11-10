#!/usr/bin/env python3
"""Synthetic Mach-O metadata only; these controls do not qualify a macOS build."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('shared_build', Path(__file__).with_name('build.py'))
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)


def load_commands(dependencies=(), rpaths=(), identity=None):
    commands = [('LC_RPATH', 'path', value) for value in rpaths]
    if identity is not None:
        commands.append(('LC_ID_DYLIB', 'name', identity))
    commands.extend((kind, 'name', value) for kind, value in dependencies)
    commands.insert(0, ('LC_SEGMENT_64', 'segname', '__TEXT'))
    return '\n'.join(f'Load command {index}\n          cmd {kind}\n      cmdsize 64\n'
                     f'         {field} {value} (offset 24)'
                     for index, (kind, field, value) in enumerate(commands)) + '\n'


class DarwinToolchain(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='mlf-darwin-toolchain-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.metadata = {}
        self.dependencies = {}
        self.architectures = {}
        self.slice_metadata = {}
        self.inspected = []
        self.sdk = self.root / 'Xcode with spaces/SDKs/MacOSX.sdk'
        self.make_file(self.sdk / 'SDKSettings.json')
        self.cache_dir = self.root / 'dyld'
        self.make_file(self.cache_dir / 'dyld_shared_cache_arm64e', b'cache data')
        self.make_file(self.cache_dir / 'dyld_shared_cache_arm64e.01', b'cache subfile')
        self.make_file(self.cache_dir / 'dyld_shared_cache_arm64e.map', b'/usr/lib/libSystem.B.dylib\n')
        self.ghc = self.image('ghc/bin/ghc-9.14.1')
        self.libdir = self.root / 'ghc/lib'
        self.libdir.mkdir()
        self.apple = self.image('Xcode with spaces/Toolchains/Default.xctoolchain/usr/bin/clang')
        self.lipo = self.image('Xcode with spaces/Toolchains/Default.xctoolchain/usr/bin/lipo')
        self.cc = self.image('homebrew/Cellar/llvm@19/19.1.7/bin/clang-19',
                             ['@rpath/libclang-cpp.dylib'], ['@loader_path/../lib'])
        self.clang_library = self.image('homebrew/Cellar/llvm@19/19.1.7/lib/libclang-cpp.dylib',
                                       ['/usr/lib/libSystem.B.dylib'], identity='@rpath/libclang-cpp.dylib')

    def make_file(self, path, data=b'fixture bytes'):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def image(self, relative, dependencies=(), rpaths=(), identity=None):
        path = self.make_file(self.root / relative, relative.encode())
        self.set_commands(path, dependencies, rpaths, identity)
        return path

    def set_commands(self, path, dependencies=(), rpaths=(), identity=None):
        self.dependencies[path] = dependencies
        self.metadata[path] = load_commands([('LC_LOAD_DYLIB', name) for name in dependencies], rpaths, identity)

    def fake_path(self, path):
        if str(path) == '/System/Volumes/Preboot/Cryptexes/OS/System/Library/dyld':
            return self.cache_dir
        if str(path) == '/Library/Developer/CommandLineTools/usr/lib':
            return self.root / 'absent-command-line-tools'
        return Path(path)

    def check_output(self, argv, **kwargs):
        argv = list(map(str, argv))
        if argv == ['xcrun', '--show-sdk-path']:
            return str(self.sdk) + '\n'
        if argv[:2] == ['xcrun', '--find']:
            return str(self.lipo if argv[2] == 'lipo' else self.apple) + '\n'
        if argv[:2] == ['/usr/bin/file', '-b']:
            return 'Mach-O 64-bit arm64\n' if Path(argv[2]) in self.metadata else 'data\n'
        raise AssertionError(argv)

    def run_tool(self, argv, **kwargs):
        argv = list(map(str, argv))
        self.inspected.append(argv)
        if argv[1:2] == ['-archs']:
            output = self.architectures.get(Path(argv[2]), 'arm64')
        elif argv[:2] == ['/usr/bin/otool', '-arch'] and argv[3] == '-l':
            output = self.slice_metadata.get((Path(argv[4]), argv[2]), self.metadata[Path(argv[4])])
        elif argv[:2] == ['/usr/bin/otool', '-L']:
            # Also model the old resolver for the before/after regression.
            output = '\n'.join(f'\t{name} (compatibility version 1.0.0, current version 1.0.0)'
                               for name in self.dependencies[Path(argv[2])])
        else:
            raise AssertionError(argv)
        return subprocess.CompletedProcess(argv, 0, output, '')

    def closure(self, paths=None):
        with patch.object(build, 'Path', side_effect=self.fake_path), \
                patch.object(build.subprocess, 'check_output', side_effect=self.check_output), \
                patch.object(build.subprocess, 'run', side_effect=self.run_tool), \
                patch.dict(build.os.environ, {}, clear=True):
            return build.darwin_toolchain_inputs(paths or {self.ghc, self.cc}, self.ghc, self.libdir)

    def test_homebrew_rpath_and_transitive_library_are_hashed(self):
        llvm = self.image('homebrew/Cellar/llvm@19/19.1.7/lib/libLLVM.dylib')
        self.set_commands(self.clang_library, ['@loader_path/libLLVM.dylib', '/usr/lib/libSystem.B.dylib'])
        result = self.closure()
        for path in [self.cc, self.clang_library, llvm, self.sdk / 'SDKSettings.json',
                     *self.cache_dir.iterdir()]:
            self.assertEqual(result['files'][str(path)], build.sha(path))
        self.assertEqual(result['system_dylibs'], ['/usr/lib/libSystem.B.dylib'])
        self.assertIn('experimental', result['platform_qualification'])

    def test_arm64e_only_system_tool_uses_its_actual_slice(self):
        self.architectures[self.apple] = 'arm64e'
        self.closure()
        self.assertIn(['/usr/bin/otool', '-arch', 'arm64e', '-l', str(self.apple)], self.inspected)
        self.assertNotIn(['/usr/bin/otool', '-arch', 'arm64', '-l', str(self.apple)], self.inspected)

    def test_universal_image_does_not_inspect_intel_dependencies(self):
        self.architectures[self.cc] = 'x86_64 arm64'
        self.architectures[self.apple] = 'x86_64 arm64e'
        self.slice_metadata[self.cc, 'x86_64'] = load_commands([('LC_LOAD_DYLIB', '/missing/intel.dylib')])
        self.closure()
        self.assertTrue(all(argv[2] != 'x86_64' for argv in self.inspected if argv[0] == '/usr/bin/otool'))

    def test_both_native_slices_keep_distinct_rpath_closures(self):
        self.architectures[self.cc] = 'arm64 arm64e x86_64'
        ordinary = self.image('ordinary/libnative.dylib')
        hardened = self.image('hardened/libnative.dylib')
        for architecture, library in [('arm64', ordinary), ('arm64e', hardened)]:
            self.slice_metadata[self.cc, architecture] = load_commands(
                [('LC_LOAD_DYLIB', '@rpath/libnative.dylib')], [str(library.parent)])
        files = self.closure()['files']
        self.assertIn(str(ordinary), files)
        self.assertIn(str(hardened), files)
        hardened.unlink()
        with self.assertRaisesRegex(RuntimeError, 'cannot resolve Mach-O dependency'):
            self.closure()

    def test_absent_native_slice_and_failed_slice_inspection_fail_closed(self):
        for architectures in ['x86_64', 'i386 x86_64']:
            with self.subTest(architectures=architectures):
                self.architectures[self.cc] = architectures
                with self.assertRaisesRegex(RuntimeError, 'no supported Darwin toolchain slice'):
                    self.closure()
        with patch.object(self, 'run_tool', return_value=subprocess.CompletedProcess([], 1, '', 'invalid image')):
            with self.assertRaisesRegex(RuntimeError, 'lipo failed'):
                self.closure()

    def test_selected_lipo_and_its_dependencies_are_hashed(self):
        library = self.image('lipo-support/libLipo.dylib')
        self.set_commands(self.lipo, [str(library)])
        files = self.closure()['files']
        self.assertEqual(files[str(self.lipo)], build.sha(self.lipo))
        self.assertEqual(files[str(library)], build.sha(library))
        inspections = [argv for argv in self.inspected if argv[1] == '-archs']
        self.assertTrue(inspections)
        self.assertTrue(all(argv[0] == str(self.lipo) for argv in inspections))

    def test_transitive_native_slice_contexts_cannot_borrow_each_others_rpaths(self):
        self.architectures[self.cc] = 'arm64 arm64e'
        child = self.image('plugins/shared-child.dylib', ['@rpath/libnative.dylib'])
        self.architectures[child] = 'arm64 arm64e'
        ordinary = self.image('ordinary/libnative.dylib')
        hardened = self.image('hardened/libnative.dylib')
        for architecture, library in [('arm64', ordinary), ('arm64e', hardened)]:
            self.slice_metadata[self.cc, architecture] = load_commands(
                [('LC_LOAD_DYLIB', str(child))], [str(library.parent)])
        files = self.closure()['files']
        self.assertIn(str(ordinary), files)
        self.assertIn(str(hardened), files)
        hardened.unlink()
        with self.assertRaisesRegex(RuntimeError, 'cannot resolve Mach-O dependency'):
            self.closure()

    def test_malformed_unknown_and_repeated_slice_names_fail_closed(self):
        for architectures in ['', 'arm64 garbage', 'arm64 arm64', 'Architectures: arm64']:
            with self.subTest(architectures=architectures):
                self.architectures[self.cc] = architectures
                with self.assertRaisesRegex(RuntimeError, 'malformed or unsupported Mach-O slice list'):
                    self.closure()

    def test_same_basename_outside_rpaths_is_never_used(self):
        self.make_file(self.libdir / 'unrelated/libclang-cpp.dylib')
        result = self.closure()
        self.assertIn(str(self.clang_library), result['files'])
        self.assertNotIn(str(self.libdir / 'unrelated/libclang-cpp.dylib'), result['files'])

    def test_missing_rpath_target_rejects_even_with_unique_basename(self):
        self.clang_library.unlink()
        self.make_file(self.libdir / 'libclang-cpp.dylib')
        with self.assertRaisesRegex(RuntimeError, 'cannot resolve Mach-O dependency'):
            self.closure()

    def test_subdirectory_suffix_and_paths_with_spaces_are_preserved(self):
        dependency = self.image('Xcode with spaces/lib/nested/libc++.dylib')
        self.set_commands(self.cc, ['@rpath/nested/libc++.dylib'], [str(dependency.parent.parent)])
        self.assertIn(str(dependency), self.closure()['files'])

    def test_extra_token_slashes_cannot_select_an_absolute_decoy(self):
        decoy = self.image('decoy/lib.dylib')
        for token in ['@rpath', '@loader_path', '@executable_path']:
            with self.subTest(token=token):
                base = self.clang_library.parent if token == '@rpath' else self.cc.parent
                relative = str(decoy).lstrip('/')
                actual = self.image(str((base / relative).relative_to(self.root)))
                self.set_commands(self.cc, [token + '//' + relative], [str(base)])
                files = self.closure()['files']
                self.assertIn(str(actual), files)
                self.assertNotIn(str(decoy), files)

    def test_unused_origin_rpath_on_ghc_helper_is_inert(self):
        self.set_commands(self.ghc, ['/usr/lib/libSystem.B.dylib'],
                          ['$ORIGIN/../../../lib/aarch64-osx-ghc-9.14.1-a591'])
        self.assertIn(str(self.ghc), self.closure()['files'])

    def test_unused_opaque_rpath_survives_absolute_dependency_traversal(self):
        child = self.image('plugins/helper.dylib', ['/usr/lib/libSystem.B.dylib'])
        self.set_commands(self.ghc, [str(child)], ['$ORIGIN/../lib'])
        self.assertIn(str(child), self.closure()['files'])

    def test_successful_rpath_candidate_does_not_consult_later_origin(self):
        self.set_commands(self.cc, ['@rpath/libclang-cpp.dylib'],
                          ['@loader_path/../lib', '$ORIGIN/../lib'])
        self.assertIn(str(self.clang_library), self.closure()['files'])

    def test_active_origin_before_valid_rpath_is_not_silently_skipped(self):
        self.set_commands(self.cc, ['@rpath/libclang-cpp.dylib'],
                          ['$ORIGIN/../lib', '@loader_path/../lib'])
        with self.assertRaisesRegex(RuntimeError, r'unsupported Mach-O path: \$ORIGIN'):
            self.closure()

    def test_descendant_rpath_search_consults_opaque_inherited_entries(self):
        child = self.image('plugins/helper.dylib', ['@rpath/libclang-cpp.dylib'])
        self.set_commands(self.cc, [str(child)], ['$ORIGIN/../lib', '@loader_path/../lib'])
        with self.assertRaisesRegex(RuntimeError, r'unsupported Mach-O path: \$ORIGIN'):
            self.closure()

    def test_rpath_order_selects_first_existing_library(self):
        first = self.image('first/libclang-cpp.dylib')
        second = self.image('second/libclang-cpp.dylib')
        self.set_commands(self.cc, ['@rpath/libclang-cpp.dylib'], [str(self.root / 'absent'), str(first.parent), str(second.parent)])
        result = self.closure()['files']
        self.assertIn(str(first), result)
        self.assertNotIn(str(second), result)

    def test_inherited_rpath_is_anchored_to_declaring_loader(self):
        child = self.image('plugins/child.dylib', ['@rpath/libclang-cpp.dylib'])
        self.set_commands(self.cc, [str(child)], ['@loader_path/../lib'])
        self.assertIn(str(self.clang_library), self.closure()['files'])

    def test_child_rpaths_precede_inherited_paths(self):
        child_library = self.image('plugins/libclang-cpp.dylib')
        child = self.image('plugins/child.dylib', ['@rpath/libclang-cpp.dylib'], ['@loader_path'])
        self.set_commands(self.cc, [str(child)], ['@loader_path/../lib'])
        files = self.closure()['files']
        self.assertIn(str(child_library), files)
        self.assertNotIn(str(self.clang_library), files)

    def test_executable_path_keeps_the_root_through_transitive_loads(self):
        child = self.image('plugins/child.dylib', ['@executable_path/../lib/libclang-cpp.dylib'])
        self.set_commands(self.cc, [str(child)])
        self.assertIn(str(self.clang_library), self.closure()['files'])

    def test_executable_path_in_rpath(self):
        self.set_commands(self.cc, ['@rpath/libclang-cpp.dylib'], ['@executable_path/../lib'])
        self.assertIn(str(self.clang_library), self.closure()['files'])

    def test_shared_library_is_revisited_for_each_executable_context(self):
        other = self.image('other/bin/cc')
        other_library = self.image('other/lib/libclang-cpp.dylib')
        child = self.image('plugins/child.dylib', ['@executable_path/../lib/libclang-cpp.dylib'])
        self.set_commands(self.cc, [str(child)])
        self.set_commands(other, [str(child)])
        result = self.closure({self.cc, other})['files']
        self.assertIn(str(self.clang_library), result)
        self.assertIn(str(other_library), result)

    def test_dylib_id_is_not_a_load_dependency(self):
        self.set_commands(self.clang_library, identity='@rpath/nonexistent-self-id.dylib')
        self.assertIn(str(self.clang_library), self.closure()['files'])

    def test_cycles_terminate_without_omitting_other_dependencies(self):
        child = self.image('plugins/child.dylib', [str(self.clang_library)], ['@loader_path'])
        self.set_commands(self.clang_library, [str(child)])
        result = self.closure()['files']
        self.assertIn(str(child), result)
        self.assertLess(len(self.inspected), 20)

    def test_missing_absolute_or_loader_dependency_fails(self):
        for name in [str(self.root / 'missing.dylib'), '@loader_path/missing.dylib']:
            with self.subTest(name=name):
                self.set_commands(self.cc, [name])
                with self.assertRaises((RuntimeError, FileNotFoundError)):
                    self.closure()

    def test_unsupported_relative_dependency_and_rpath_fail(self):
        for dependency, rpaths in [('librelative.dylib', []), ('@rpath/libclang-cpp.dylib', ['relative']),
                                   ('@rpath/libclang-cpp.dylib', ['@rpath/recursive'])]:
            with self.subTest(dependency=dependency, rpaths=rpaths):
                self.set_commands(self.cc, [dependency], rpaths)
                with self.assertRaisesRegex(RuntimeError, 'unsupported Mach-O'):
                    self.closure()

    def test_system_library_must_be_present_in_shared_cache(self):
        self.set_commands(self.cc, ['/usr/lib/not-in-cache.dylib'])
        with self.assertRaisesRegex(RuntimeError, 'system dylib absent'):
            self.closure()

    def test_map_without_primary_cache_bytes_fails(self):
        (self.cache_dir / 'dyld_shared_cache_arm64e').unlink()
        with self.assertRaisesRegex(RuntimeError, 'missing primary dyld shared-cache file'):
            self.closure()
        (self.cache_dir / 'dyld_shared_cache_arm64e.01').unlink()
        with self.assertRaisesRegex(RuntimeError, 'missing primary dyld shared-cache file'):
            self.closure()

    def test_cache_map_requires_exact_install_name_lines(self):
        cache_map = self.cache_dir / 'dyld_shared_cache_arm64e.map'
        for text in ['/usr/lib/libSystem.B.dylib.extra\n',
                     '/usr/lib/libSystem.B.dylib extra\n',
                     '\t/usr/lib/libSystem.B.dylib\n']:
            with self.subTest(text=text):
                cache_map.write_text(text)
                with self.assertRaisesRegex(RuntimeError, 'system dylib absent'):
                    self.closure()
        # Apple emits image names alone, then indented segment-address rows.
        cache_map.write_text('/usr/lib/libSystem.B.dylib\n\t\t__TEXT 0x100 -> 0x200\n')
        self.assertEqual(self.closure()['system_dylibs'], ['/usr/lib/libSystem.B.dylib'])

    def test_non_regular_dependency_fails(self):
        self.set_commands(self.cc, ['@loader_path/../lib'])
        with self.assertRaisesRegex(RuntimeError, 'not a regular file'):
            self.closure()

    def test_weak_reexport_upward_and_lazy_dependencies_are_not_skipped(self):
        for kind in ['LC_LOAD_WEAK_DYLIB', 'LC_REEXPORT_DYLIB', 'LC_LOAD_UPWARD_DYLIB', 'LC_LAZY_LOAD_DYLIB']:
            with self.subTest(kind=kind):
                self.metadata[self.cc] = load_commands([(kind, str(self.clang_library))])
                self.assertIn(str(self.clang_library), self.closure()['files'])
                self.metadata[self.cc] = load_commands([(kind, str(self.root / 'absent.dylib'))])
                with self.assertRaises((RuntimeError, FileNotFoundError)):
                    self.closure()

    def test_failed_otool_and_missing_command_fields_fail_closed(self):
        for output in ['', 'garbled metadata', 'Load command 0\n cmd LC_RPATH\n cmdsize 32\n',
                       'Load command 0\n cmd LC_LOAD_DYLIB\n cmdsize 64\n']:
            with self.subTest(output=output):
                self.metadata[self.cc] = output
                with self.assertRaisesRegex(RuntimeError, 'malformed Mach-O'):
                    self.closure()
        original = self.run_tool
        def bad_otool(argv, **kwargs):
            return (subprocess.CompletedProcess(argv, 1, '', 'bad native slice')
                    if str(argv[0]) == '/usr/bin/otool' else original(argv, **kwargs))
        with patch.object(self, 'run_tool', side_effect=bad_otool):
            with self.assertRaisesRegex(RuntimeError, 'otool failed'):
                self.closure()

    def test_non_macho_dependency_is_not_silently_skipped(self):
        self.metadata.pop(self.clang_library)
        with self.assertRaisesRegex(RuntimeError, 'not a Mach-O image'):
            self.closure()

    def test_loader_environment_overrides_are_rejected(self):
        for name in ['DYLD_LIBRARY_PATH', 'DYLD_SHARED_CACHE_DIR', 'DYLD_SHARED_REGION']:
            with self.subTest(name=name), patch.dict(build.os.environ, {name: str(self.root)}, clear=True):
                with self.assertRaisesRegex(RuntimeError, 'unsupported Mach-O loader environment'):
                    build.darwin_toolchain_inputs({self.cc}, self.ghc, self.libdir)
        self.metadata[self.cc] = 'Load command 0\n cmd LC_DYLD_ENVIRONMENT\n name DYLD_LIBRARY_PATH=/tmp (offset 12)\n'
        with self.assertRaisesRegex(RuntimeError, 'unsupported Mach-O loader environment'):
            self.closure()

    def test_symlink_aliases_resolve_to_hashed_file(self):
        alias = self.clang_library.parent / 'alias.dylib'
        alias.symlink_to(self.clang_library.name)
        self.set_commands(self.cc, ['@rpath/alias.dylib'], ['@loader_path/../lib'])
        result = self.closure()['files']
        self.assertIn(str(self.clang_library), result)
        self.assertNotIn(str(alias), result)


if __name__ == '__main__':
    unittest.main()
