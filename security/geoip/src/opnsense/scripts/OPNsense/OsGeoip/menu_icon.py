#!/usr/local/bin/python3

"""
    menu_icon.py
    Version: 2.0.0

    Copyright (C) 2026 Async IT
    All rights reserved.

    Redistribution and use in source and binary forms, with or without
    modification, are permitted provided that the following conditions are met:

    1. Redistributions of source code must retain the above copyright notice,
       this list of conditions and the following disclaimer.

    2. Redistributions in binary form must reproduce the above copyright
       notice, this list of conditions and the following disclaimer in the
       documentation and/or other materials provided with the distribution.

    THIS SOFTWARE IS PROVIDED ``AS IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES,
    INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY
    AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
    AUTHOR BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY,
    OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
    SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
    INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
    CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
    ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
    POSSIBILITY OF SUCH DAMAGE.

    --------------------------------------------------------------------------------------

    Adds or removes the custom menu icon of the plugin (globe with a small shield).

    OPNsense menu entries only accept CSS classes and plugins cannot load their own
    stylesheet on every page, so a small CSS block is appended to the main.css file of
    each installed theme. The block is delimited by markers, so it can be replaced or
    removed safely. OPNsense updates restore the original theme files: the block is
    applied again by the rc.syshook.d "start" and "update" hooks of the plugin.

    The menu entry also carries the "fa-globe" class: when the block is missing, the
    standard globe icon is displayed instead.

    Commands:
        install   add (or refresh) the CSS block in every theme
        remove    remove the CSS block from every theme

    Changelog:
        2.0.0  Renamed for os-geoip (class, markers and icon path use "osgeoip").
        1.1.0  Initial version (introduced with plugin version 1.1).
"""

import glob
import os
import re
import sys

THEME_STYLESHEETS = '/usr/local/opnsense/www/themes/*/build/css/main.css'
ICON_URL = '/ui/img/osgeoip/menu-icon.svg'

BLOCK_BEGIN = '/* osgeoip-menu-icon:begin */'
BLOCK_END = '/* osgeoip-menu-icon:end */'
BLOCK_PATTERN = re.compile(r'\n?' + re.escape(BLOCK_BEGIN) + r'.*?' + re.escape(BLOCK_END) + r'\n?', re.S)

# The icon is drawn in the current text color through a CSS mask, so it follows
# the colors of every theme (light, dark, hover, active entry).
CSS_BLOCK = '\n'.join([
    BLOCK_BEGIN,
    '.fa.osgeoip-icon:before {',
    '    content: "";',
    '    display: inline-block;',
    '    width: 1em;',
    '    height: 1em;',
    '    vertical-align: -0.125em;',
    '    background-color: currentColor;',
    '    -webkit-mask: url("%s") no-repeat center / contain;' % ICON_URL,
    '    mask: url("%s") no-repeat center / contain;' % ICON_URL,
    '}',
    BLOCK_END,
])


def update_stylesheet(path, install):
    """Adds or removes the CSS block in one stylesheet. Returns True when the file changed."""
    with open(path) as handle:
        original = handle.read()

    content = BLOCK_PATTERN.sub('\n', original).rstrip('\n') + '\n'
    if install:
        content += CSS_BLOCK + '\n'

    if content == original:
        return False

    # Atomic replacement, keeping the permissions of the original file.
    temporary_path = path + '.osgeoip.tmp'
    with open(temporary_path, 'w') as handle:
        handle.write(content)
    os.chmod(temporary_path, os.stat(path).st_mode)
    os.replace(temporary_path, path)
    return True


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ('install', 'remove'):
        print('usage: menu_icon.py install|remove')
        return 1

    install = sys.argv[1] == 'install'
    for path in sorted(glob.glob(THEME_STYLESHEETS)):
        try:
            if update_stylesheet(path, install):
                print('%s: %s' % ('updated' if install else 'cleaned', path))
        except OSError as error:
            print('skipped %s: %s' % (path, error))
    return 0


if __name__ == '__main__':
    sys.exit(main())
