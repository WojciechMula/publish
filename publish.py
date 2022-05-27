#!/usr/bin/env python3

import os
import sys
import logging
import argparse
import subprocess
import re
from pathlib import Path
from itertools import chain


ACTION_FIXUP = 'fixup'
ACTION_MISSING = 'missing'
ACTION_BACKUP = 'backup'


known_actions = {
    ACTION_FIXUP,
    ACTION_MISSING,
    ACTION_BACKUP,
}

class ProgramError(Exception):
    pass


def main():
    args = parse_args()
    if args.use_git:
        git = Git(args.path)
    else:
        git = DummyGit()

    app = Application(args, git)
    app.run()


class Application:
    def __init__(self, args, git):
        self.args = args
        self.git  = git

    def run(self):
        if self.args.action == ACTION_FIXUP:
            self.action_fixup()
        elif self.args.action == ACTION_MISSING:
            self.action_print_missing()
        elif self.args.action == ACTION_BACKUP:
            self.action_backup_source_photos()
        else:
            self.action_not_published(self.args.action)

    def action_fixup(self):
        for workdir in self.workdirs:
            p = Directory(workdir, self.args.services)
            p.action_fixup(self.git)

    def action_print_missing(self):
        for workdir in self.workdirs:
            p = Directory(workdir, self.args.services)
            p.action_print_missing()

    def action_backup_source_photos(self):
        for workdir in self.workdirs:
            p = Directory(workdir, self.args.services)
            p.action_backup_source_photos()

    def action_not_published(self, service):
        for workdir in self.workdirs:
            p = Directory(workdir, self.args.services)
            p.action_not_published(service)

    @property
    def workdirs(self):
        for p in self.all_workdirs:
            path = p / "publish"
            if path.exists():
                yield path

    @property
    def all_workdirs(self):
        """
        We expect the following structure:

            2022-01-01/
                a/      *
                b/      *
            2022-01-02/ *
            2022-01-03/ *

        or:

            01/
                2022-01-01/ *
                2022-01-02/ *
                2022-01-03/
                    a/      *
                    b/      *
            02/
                2022-01-02/ *

        Directories marked with '*' are returned
        """
        workdirs = []

        for month in ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"]:
            path = self.args.path / month
            if path.exists():
                workdirs.append(path)

        if not workdirs:
            workdirs.append(self.args.path)

        def roots():
            for workdir in workdirs:
                for path in workdir.iterdir():
                    if re.match("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", path.name):
                        yield path

        for path in sorted(roots()):
            subdirs = False
            for letter in "abcdefgh":
                p = path / letter
                if p.exists():
                    subdirs = True
                    yield p

            if not subdirs:
                yield path


def parse_args(arguments=None):
    parser = argparse.ArgumentParser(description="Manage photo collection")
    parser.add_argument("action",
                        nargs='?',
                        help="action to peform (default: fixup)")
    parser.add_argument("path",
                        nargs='?',
                        type=Path,
                        default=Path('.'),
                        help="working directory (default: current directory)")
    parser.add_argument("--config",
                        nargs='?',
                        type=Path,
                        default=Path('~/.config/publish/settings.py').expanduser(),
                        help="location of configuration file")

    args = parser.parse_args(arguments)
    if not args.config.exists():
        parser.error(f'{args.config} does not exist')

    try:
        objects = {}
        exec(args.config.read_text(), objects)

        args.services = objects.get('services', [])
        args.use_git = objects.get('git', False)
    except Exception as e:
        parser.error(f'{args.config} is invalid: {e}')

    if not args.services:
        parser.error(f'{args.config} does not define any services')

    if args.action is None:
        args.action = ACTION_FIXUP
    elif args.action not in known_actions and args.action not in args.services:
        tmp = ', '.join(chain(known_actions, args.services))
        parser.error(f'action must be on of {tmp}')

    return args


def logger():
    log = logging.getLogger(__name__)
    log.setLevel(logging.INFO)

    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))

    log.addHandler(ch)

    return log


log = logger()


SOURCE_RAW  = 1
SOURCE_JPEG = 2
TARGET_JPEG = 3
SMALL_JPEG  = 4


class Directory:
    def __init__(self, rootdir, known_subdirs):
        self.rootdir = rootdir
        self.known_subdirs = known_subdirs

        self.sources = []
        for path in self.rootdir.glob('*'):
            if not path.is_dir():
                typ = self.classify(path)
                if typ == SOURCE_RAW:
                    self.sources.append(RawSourceImage(path))
                elif typ == SOURCE_JPEG:
                    self.sources.append(JpegSourceImage(path))


    def classify(self, path):
        if path.is_symlink():
            ext = path.suffix.lower()
            if ext in ('.jpg', '.jpeg'):
                return SOURCE_JPEG
            elif ext in ('.nef', '.cr3'):
                return SOURCE_RAW


    def action_fixup(self, git):
        self.__add_missing_subdirs()
        self.__create_missing_small_images()
        self.__add_new_small_files()
        self.__fixup_source_photos_links()
        self.__fixup_published_links()
        self.__add_files_to_repository(git)


    def action_print_missing(self):
        for source in self.sources:
            if not source.large.exists():
                print(source.path)


    def action_not_published(self, service):
        d = self.rootdir / service
        if not d.exists():
            return

        for path in d.glob('*'):
            if path.is_symlink():
               print(path)


    def action_backup_source_photos(self):
        bakdir = self.rootdir / '.backup'
        if not bakdir.exists():
            log.info("Adding directory %s", bakdir)
            bakdir.mkdir()

        for source in self.sources:
            backup = bakdir / source.path.name
            if backup.exists():
                continue

            log.info(f"Adding hardlink to {source.path} at {backup}")
            source.path.link_to(backup)


    def __add_missing_subdirs(self):
        for path in self.missing_subdirs:
            log.info("Adding directory %s", path)
            path.mkdir()


    def __create_missing_small_images(p):
        SMALL_JPEG_WIDTH = 1024 # in pixels

        CREATE = 1
        UPDATE = 2

        for source in p.sources:
            large, small = source.large, source.small
            if not large.exists():
                continue

            action = None
            if small.exists():
                if small.stat().st_mtime < large.stat().st_mtime:
                    action = UPDATE
            else:
                action = CREATE

            if action is None:
                continue

            if action == CREATE:
                log.info("Creating %s from %s", small, large)
            else:
                log.info("Updating %s from %s", small, large)

            cmd = f'convert -verbose "{large}" -resize {SMALL_JPEG_WIDTH}x "{small}"'
            ret = os.system(cmd)
            if ret != 0:
                log.error(cmd)
                log.error(f'the above command failed with error code {ret}')


    def __add_new_small_files(p):
        for subdir, names in p.new_small_images:
            for name in names:
                log.info("Adding link to %s in %s", name, subdir.name)

                link = subdir / name
                target = Path('..') / name

                link.symlink_to(target)


    def __fixup_source_photos_links(self):
        for source in self.sources:
            path = source.path
            link = Path(os.readlink(path))
            if not link.is_absolute():
                continue

            newlink = Path('..') / path.name
            log.info(f"Replacing link {path} from {link} to {newlink}")
            path.unlink()
            path.symlink_to(newlink)


    def __fixup_published_links(self):
        for path in self.published_small:
            link = Path(os.readlink(path))
            if (path.parent / link).exists():
                continue

            newlink = Path('..') / Path('..') / path.name
            log.info(f"Replacing link {path} from {link} to {newlink}")
            path.unlink()
            path.symlink_to(newlink)

    def __add_files_to_repository(self, git):
        for path in self.rootdir.glob('**/*.*'):
            if path.is_symlink():
                git.add_file(path)

    @property
    def missing_large(self):
        for source in self.sources:
            large = source.large
            if not large.exists():
                yield large

    @property
    def missing_small(self):
        for source in self.sources:
            small = source.small
            large = source.large
            if large.exists() and not small.exists():
                yield (large, small)

    @property
    def missing_subdirs(self):
        for subdir in self.known_subdirs:
            path = self.rootdir / subdir
            if not path.exists():
                yield path

            path = path / 'published'
            if not path.exists():
                yield path

    @property
    def existing_small(self):
        for source in self.sources:
            small = source.small
            if small.exists():
                yield small

    @property
    def published_small(self):
        pattern = '*_small*'
        for subdir in self.known_subdirs:
            d = self.rootdir / subdir / 'published'
            if not d.exists():
                continue

            yield from d.glob(pattern)

    @property
    def new_small_images(self):
        all_small = {p.name for p in self.existing_small}
        pattern = '*_small*'
        for subdir in self.known_subdirs:
            subdir = self.rootdir / subdir
            if not subdir.exists():
                continue

            managed_small = set()
            for path in subdir.glob(pattern):
                managed_small.add(path.name)

            d = subdir / 'published'
            if d.exists():
                for path in d.glob(pattern):
                    managed_small.add(path.name)

            new = all_small - managed_small
            if new:
                yield subdir, new


class RawSourceImage:
    def __init__(self, path):
        self.path = path

    @property
    def large(self):
        p = self.path
        for suffix in ['.JPG', '.jpg']:
            p1 = p.with_suffix(suffix)
            if p1.exists():
                return p1

        return p.with_suffix(".JPG")

    @property
    def small(self):
        p = self.path
        return p.parent / (p.stem + "_small.jpg")


class JpegSourceImage:
    def __init__(self, path):
        self.path = path

    @property
    def large(self):
        p = self.path
        extensions = ('jpg', 'JPG', 'jpeg', 'JPEG')
        for ext in extensions:
            p1 = p.parent / (p.stem + "_processed." + ext)
            if p1.exists():
                return p1

        return p

    @property
    def small(self):
        p = self.path
        return p.parent / (p.stem + "_small.jpg")


class Git:
    def __init__(self, rootdir):
        rootdir = rootdir.absolute()
        self.__files = None
        self.gitarg  = f"--git-dir={rootdir}/.git --work-tree={rootdir}"

    @property
    def files(self):
        if self.__files is None:
            ret = self.execute("ls-files")
            self.__files = {Path(s.decode('utf-8')) for s in ret.stdout.splitlines()}
        
        return self.__files

    def add_file(self, path):
        if path in self.files:
            return

        log.info(f"Adding to git {path}")
        self.execute(f"add -f {path}")

    def execute(self, cmd):
        command = f"git {self.gitarg} {cmd}"
        try:
            return subprocess.run(command, shell=True, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            raise ProgramError(f'{command}: ' + e.stderr.decode('utf-8'))


class DummyGit:
    def add_file(self, path):
        pass


if __name__ == '__main__':
    try:
        main()
    except ProgramError as e:
        print(e)
        sys.exit(1)
