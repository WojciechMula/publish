import os
import io
import unittest
import tempfile
import shutil
import contextlib
from pathlib import Path
from publish import Application, Git, parse_args, ACTION_FIXUP, ACTION_MISSING, ACTION_BACKUP


SETTINGS="""\
services = ['test1', 'test2']
git = True
"""

known_subdirs = ['test1', 'test2']


def create_settings(directory):
    path = Path(directory) / 'settings.py'
    path.write_text(SETTINGS)

    return path


class TestFixup(unittest.TestCase):
    def test_fixup_creates_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            # given
            settings = create_settings(directory)
            args = parse_args([ACTION_FIXUP,
                               directory,
                               '--config', str(settings)])

            subdir = args.path / '2022-01-01'
            subdir.mkdir()

            publish = subdir / 'publish'
            publish.mkdir()

            git = Git(args.path)
            git.execute("init")

            # when
            app = Application(args, git)
            app.run()

            # then
            for subdir in known_subdirs:
                assert (publish / subdir).is_dir()
                assert (publish / subdir / 'published').is_dir()

    def test_create_missing_small_images(self):
        with tempfile.TemporaryDirectory() as directory:
            # given
            settings = create_settings(directory)
            args = parse_args([ACTION_FIXUP,
                               directory,
                               '--config', str(settings)])

            subdir = args.path / '2022-01-01'
            subdir.mkdir()

            publish = subdir / 'publish'
            publish.mkdir()

            git = Git(args.path)
            git.execute("init")

            photo1 = publish / 'DSC_0001.JPG'
            photo2 = publish / 'DSC_0002.JPG'
            photo3 = publish / 'DSC_0002_processed.JPG'

            source = Path('sample.jpg').absolute()
            assert source.exists()

            photo1.symlink_to(source)
            photo2.symlink_to(source)
            shutil.copy(source, photo3)

            # when
            app = Application(args, git)
            app.run()

            # then
            assert (publish / 'DSC_0001_small.jpg').exists()
            assert (publish / 'DSC_0001_small.jpg').is_file()
            assert (publish / 'DSC_0002_small.jpg').exists()
            assert (publish / 'DSC_0002_small.jpg').is_file()
            for subdir in known_subdirs:
                path = publish / subdir
                assert (path / 'DSC_0001_small.jpg').exists()
                assert (path / 'DSC_0001_small.jpg').is_symlink()
                assert (path / 'DSC_0002_small.jpg').exists()
                assert (path / 'DSC_0002_small.jpg').is_symlink()


    def test_add_missing_small_images(self):
        with tempfile.TemporaryDirectory() as directory:
            # given
            settings = create_settings(directory)
            args = parse_args([ACTION_FIXUP,
                               directory,
                               '--config', str(settings)])

            subdir = args.path / '2022-01-01'
            subdir.mkdir()

            publish = subdir / 'publish'
            publish.mkdir()

            git = Git(args.path)
            git.execute("init")

            app = Application(args, git)
            app.run()

            # when (add small files)
            names = ['DSC_0001.NEF', 'DSC_0002.CR3', 'DSC_0003.JPG', 'DSC_0004.JPG']
            for name in names:
                large = publish / name
                small = publish / (large.stem + '_small.jpg')

                large.symlink_to('picture')
                small.write_text('small')

            app.run()

            # then
            for subdir in known_subdirs:
                for name in names:
                    small = publish / subdir / (large.stem + '_small.jpg')
                    assert small.is_symlink()


    def test_fixup_source_symbolic_links(self):
        with tempfile.TemporaryDirectory() as directory:
            # given
            settings = create_settings(directory)
            args = parse_args([ACTION_FIXUP,
                               directory,
                               '--config', str(settings)])

            subdir = args.path / '2022-01-01'
            subdir.mkdir()

            publish = subdir / 'publish'
            publish.mkdir()

            git = Git(args.path)
            git.execute("init")

            rootdir = Path('/mnt') / 'arch' / '2022' / '01' / '2022-01-01'
            photo1 = publish / 'DSC_0001.NEF'
            photo1.symlink_to(rootdir / photo1.name)
            photo2 = publish / 'DSC_0002.CR3'
            photo2.symlink_to(rootdir / photo2.name)
            photo3 = publish / 'DSC_0002.JPG'
            photo3.symlink_to(rootdir / photo3.name)

            # when
            app = Application(args, git)
            app.run()

            # then
            assert f'../{photo1.name}' == os.readlink(photo1)
            assert f'../{photo2.name}' == os.readlink(photo2)
            assert f'../{photo3.name}' == os.readlink(photo3)


    def test_fixup_published_symbolic_links(self):
        with tempfile.TemporaryDirectory() as directory:
            # given
            settings = create_settings(directory)
            args = parse_args([ACTION_FIXUP,
                               directory,
                               '--config', str(settings)])

            subdir = args.path / '2022-01-01'
            subdir.mkdir()

            publish = subdir / 'publish'
            publish.mkdir()

            git = Git(args.path)
            git.execute("init")

            app = Application(args, git)
            app.run()

            rootdir = Path('/mnt') / 'arch' / '2022' / '01' / '2022-01-01'
            for subdir in known_subdirs:
                published = publish / subdir / 'published'
                photo = published / 'DSC_0001_small.jpg'
                photo.symlink_to(rootdir / photo.name)

            # when
            app.run()

            # then
            for subdir in known_subdirs:
                photo = publish / subdir / 'published' / 'DSC_0001_small.jpg'
                assert f'../../{photo.name}' == os.readlink(photo)


class TestMissing(unittest.TestCase):
    def test_missing_prints_missing_processed_photos(self):
        with tempfile.TemporaryDirectory() as directory:
            # given
            settings = create_settings(directory)
            args = parse_args([ACTION_MISSING,
                               directory,
                               '--config', str(settings)])

            subdir = args.path / '2022-01-01'
            subdir.mkdir()

            publish = subdir / 'publish'
            publish.mkdir()

            git = Git(args.path)
            git.execute("init")

            photos = [('link', 'DSC_0001.JPG'), # DSC_0001 is ready -> processed.jpg exists
                      ('file', 'DSC_0001_processed.JPG'),
                      ('link', 'DSC_0002.JPG'), # DSC_0002 is ready -> (no processed.jpg, but it's fine)
                      ('link', 'DSC_0003.NEF'), # DSC_0003 is ready -> there's corresponding JPG
                      ('file', 'DSC_0003.JPG'),
                      ('link', 'DSC_0004.CR3'), # DSC_0004 is ready -> there's corresponding JPG
                      ('file', 'DSC_0004.JPG'),
                      ('link', 'DSC_0005.NEF'), # no jpeg
                      ('link', 'DSC_0006.CR3'), # no jpeg
            ]

            existing = Path('sample.jpg').absolute()
            assert existing.exists()

            for typ, photo in photos:
                path = publish / photo
                if typ == 'link':
                    path.symlink_to(existing)
                elif typ == 'file':
                    shutil.copy(existing, path)

            # when
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                app = Application(args, git)
                app.run()

            # then
            missing = {Path(line).name for line in out.getvalue().splitlines()}
            assert missing == {'DSC_0005.NEF', 'DSC_0006.CR3'}


class TestNotPublished(unittest.TestCase):
    def test_print_not_published_files(self):
        with tempfile.TemporaryDirectory() as directory:
            # given
            settings = create_settings(directory)
            args = parse_args(['test1',
                               directory,
                               '--config', str(settings)])

            test1 = args.path / '2022-01-01' / 'publish' / 'test1'
            test1.mkdir(parents=True)

            published = test1 / 'published'
            published.mkdir()

            git = Git(args.path)
            git.execute("init")

            small1 = test1 / 'DSC_0001_small.jpg'
            small2 = published / 'DSC_0002_small.jpg'
            small3 = published / 'DSC_0003_small.jpg'
            small4 = test1 / 'DSC_0004_small.jpg'

            small1.symlink_to('../DSC_0001_small.jpg')
            small2.symlink_to('../DSC_0002_small.jpg')
            small3.symlink_to('../DSC_0003_small.jpg')
            small4.symlink_to('../DSC_0004_small.jpg')

            # when
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                app = Application(args, git)
                app.run()

            # then
            files = {Path(line).name for line in out.getvalue().splitlines()}
            assert files == {'DSC_0001_small.jpg', 'DSC_0004_small.jpg'}


class TestBackup(unittest.TestCase):
    def test_backup_makes_hard_links_to_source_photos(self):
        with tempfile.TemporaryDirectory() as directory:
            # given
            settings = create_settings(directory)
            args = parse_args([ACTION_BACKUP,
                               directory,
                               '--config', str(settings)])

            subdir = args.path / '2022-01-01'
            subdir.mkdir()

            publish = subdir / 'publish'
            publish.mkdir()

            git = Git(args.path)
            git.execute("init")

            source1 = subdir / 'DSC_0001.NEF'
            source2 = subdir / 'DSC_0002.NEF'
            source3 = subdir / 'DSC_0003.NEF'

            existing = Path('sample.jpg').absolute()
            assert existing.exists()

            shutil.copy(existing, source1)
            shutil.copy(existing, source2)
            shutil.copy(existing, source3)

            photo1 = publish / 'DSC_0001.NEF'
            photo1.symlink_to('../DSC_0001.NEF')
            assert photo1.exists()

            photo2 = publish / 'DSC_0002.NEF'
            photo2.symlink_to('../DSC_0002.NEF')
            assert photo2.exists()

            photo3 = publish / 'DSC_0003.NEF'
            photo3.symlink_to('../DSC_0003.NEF')
            assert photo3.exists()

            # when
            app = Application(args, git)
            app.run()

            # then
            backup1 = publish / '.backup' / 'DSC_0001.NEF'
            assert backup1.exists()
            assert backup1.stat().st_ino == source1.stat().st_ino

            backup2 = publish / '.backup' / 'DSC_0002.NEF'
            assert backup2.exists()
            assert backup2.stat().st_ino == source2.stat().st_ino

            backup3 = publish / '.backup' / 'DSC_0003.NEF'
            assert backup3.exists()
            assert backup3.stat().st_ino == source3.stat().st_ino


if __name__ == '__main__':
    unittest.main()
