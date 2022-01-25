================================================================================
         Software to manage a collection of photos
================================================================================

:Author: Wojciech Muła
:Last update: 2022-01-25


.. contents::


Overview
--------------------------------------------------------------------------------

This is software I use to manage my collection of photos.

I split the collection by the year, month and day, like this::

    2022
    |
    +-- 01       
    |   |
    |   +- 2022-01-01
    |   +- 2022-01-02
    |   +- 2022-01-03
    |   |  +- a
    |   |  +- b
    |   +- 2022-01-04
    |   |
    .   .
    .   .  


Sometimes I need to create subdirs (``a``, ``b``, etc.), because from time to
time I use two cameras and have to avoid filename clashes.  Once the photos are
filtered, I pick a set of "best" ones worth publishing. I publish my photos in
various places, for example on Facebook. Obviously, publishing is preceded by
photo postprocessed (like cropping, adjusting contrast, colors). Then, the
final photo is resized down to some reasonable dimensions.

The problem is that selecting photos, postprocessing and publishing may span
several days, weeks or even months. I need to keep track which selected
pictures require some work, and which were already published on a certain
platform.

This software helps me in managing this very custom workflow.


Workflow
--------------------------------------------------------------------------------

1. In a directory for the given day (for example ``2022-01-01`` or
   ``2022-01-04/b``) I create subdirectory ``publish``.
2. From the main directory I select "best" photos and make **symblic
   links** to them in ``publish`` directory. These links are considered
   as "sources".
3. I process the sources using some software (currently RawTherapee__)
   and save them as JPG files in ``publish`` directory.

__ https://rawtherapee.com/

Now the program comes in:

- First of all, it downscales the processed JPGs.
- Then, adds symbolic links to the downscaled photos into subdirectories
  designed for each publishing chanell.

A sample directory structure looks like this::

    2022-01-01
    |
    +- publish/
       |
       +- DSC_0001.JPG              # original JPG file -- links to ../DSC_0001.JPG
       +- DSC_0001_processed.JPG    # processed file
       +- DSC_0001_small.jpg        # downscaled DSC_0001_processed.jpg
       +- DSC_0002.NEF              # original RAW file (this: from Nikon) -- link to ../DSC_0002.NEF
       +- DSC_0002.JPG              # processed RAW
       +- DSC_0002_small.jpg        # downscaled DSC_0002.JPG
       +- facebook/
          |
          +- DSC_0001_small.jpg     # photo awaiting for publication on Facebook
          +- published/
             |
             +- DSC_0002_small.jpg  # photo already published

When I add a new picture to the ``publish`` directory, the program creates
new symbolic links. It also keeps the symbolic link in a relative form.

Also, I keep the symbolic links in a git repository (alongside text notes,
and other tiny files). Thus the program adds new or modified symlinks to
the repository, but it's configurable.


Setup
--------------------------------------------------------------------------------

The program reads a config file ``~/.config/publish/settings.py``. It defines
what services we want to track, and if we want to use git repository. Here's
a sample content::

    # list of services we want to track (for instance Instagram, Facebook or 500px)
    services = [
        'facebook',
        'instagram',
        '500px',
    ]

    # if we want to track symbolic links with git
    git = True


Usage
--------------------------------------------------------------------------------

When the program is run without arguments, it fixes up stuff: adds missing
directories, add symbolic links to new photos, and does other maintenance,
boring things::

    $ publish       # or publish fixup

Check which photos are not postprocessed yet::

    $ publish missing

List which photos were not yet published on given service (here: Facebook)::

    $ publish facebook

Backup source images::

    $ publish backup

Backup adds **hard links** to source photos in subdir ``publish/.backup``.
