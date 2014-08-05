# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Library General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
#
# by BJ Dierkes <wdierkes@rackspace.com> 

#-----------------------------------------------------------------------------

import re
import sys
import logging
import platform

from yum.plugins import TYPE_CORE, TYPE_INTERACTIVE
from yum.Errors import UpdateError, RemoveError
from yum.constants import PLUG_OPT_STRING, PLUG_OPT_WHERE_ALL
from yumcommands import checkRootUID, checkGPGKey

requires_api_version = '2.6'
plugin_type = (TYPE_CORE, TYPE_INTERACTIVE)

global pkgs_to_not_remove, pkgs_to_remove
pkgs_to_remove = []

def config_hook(conduit):
    "Add options to Yums configuration."
    parser = conduit.getOptParser()
    
    parser.add_option('--replace-with', dest='replace_with', action='store',
        metavar='BASEPKG', help="name of the base package to replace with")

    reg = conduit.registerCommand
    conduit.registerCommand(ReplaceCommand(['replace']))

def postresolve_hook(conduit):
    """
    Remove any un-necessary package erasures.  I.e. perl-DBD-MySQL when 
    the 'mysql' packages gets removed before the mysql5x package gets 
    installed.
    """
    
    try:
        # only perform our operations (hacks) if replace command was called.
        if conduit.getCmdLine()[1][0] != 'replace':
            return
    except IndexError, e:
        # yum not called from command line?
        return

    global pkgs_to_remove
    TsInfo = conduit.getTsInfo()
    for i in TsInfo:
        if i.ts_state == 'e' and i.po not in pkgs_to_remove:
            TsInfo.remove(i.pkgtup) 

class ReplaceCommand(object):
    def __init__(self, names): 
        self.names = names

    def getNames(self):
        return self.names 

    def getUsage(self):
        return "[PACKAGE]"
    
    def getSummary(self):
        return """\
Replace a package with another that provides the same thing"""

    def doCheck(self, base, basecmd, extcmds):
        checkRootUID(base)
        checkGPGKey(base)

    def doCommand(self, base, basecmd, extcmds):
        logger = logging.getLogger("yum.verbose.main")
        print "Replacing packages takes time, please be patient..."
        global pkgs_to_remove
        pkgs_to_install = []
        pkgs_to_not_remove = []
        deps_to_resolve = []
        pkgs_with_same_srpm = []

        def msg(x):
            logger.log(logginglevels.INFO_2, x)
        def msg_warn(x):
            logger.warn(x)


        opts = base.plugins.cmdline[0]
        if len(base.plugins.cmdline[1]) <= 1:
            raise UpdateError, "Must specify a package to be replaced (i.e yum replace pkg --replace-with pkgXY)"
        if not opts.replace_with:
            raise UpdateError, "Replacement package name required (--replace-with)" 

        orig_pkg = base.plugins.cmdline[1][1]
        new_pkg = opts.replace_with

        if not base.isPackageInstalled(orig_pkg):
            raise RemoveError, "Package '%s' is not installed." % orig_pkg

        # get pkg object
        res = base.rpmdb.searchNevra(name=orig_pkg)
        if len(res) > 1:
            raise RemoveError, \
                "Multiple packages found matching '%s'.  Please remove manually." % \
                orig_pkg
        orig_pkgobject = res[0]
        pkgs_to_remove.append(orig_pkgobject)

        # find all other installed packages with same srpm (orig_pkg's subpackages)
        for pkg in base.rpmdb:
            if pkg.sourcerpm == orig_pkgobject.sourcerpm:
                pkgs_to_remove.append(pkg)
                for dep in pkg.provides_names:
                    deps_to_resolve.append(dep)

        # get new pkg object
        new_pkgs = []
        res = base.pkgSack.returnNewestByName(new_pkg)
        for i in res:
            if platform.machine() == i.arch:
                if i not in new_pkgs:
                    new_pkgs.append(i)

        # if no archs matched (maybe a i686 / i386 issue) then pass them all
        if len(new_pkgs) == 0:
            new_pkgs = res

        # clean up duplicates, for some reason yum creates duplicate package objects
        # that are the same, but different object ref so they don't compare.  here
        # we compare against returnEVR().
        final_pkgs = []
        for i in new_pkgs:
            add = True 
            for i2 in final_pkgs:
                if i.returnEVR() == i2.returnEVR() and i.arch == i2.arch:
                    add = False
            if add and i not in final_pkgs:
                final_pkgs.append(i)

        if len(final_pkgs) > 1:
            raise UpdateError, \
                "Multiple packages found matching '%s'.  Please upgrade manually." % \
                new_pkg
        new_pkgobject = new_pkgs[0]
        pkgs_to_install.append(new_pkgobject)

        orig_prefix = orig_pkg
        new_prefix = new_pkg

        # Find the original and new prefixes of packages based on their sourcerpm name
        m = re.match('(.*)-%s-%s' % (orig_pkgobject.version, orig_pkgobject.release),\
            orig_pkgobject.sourcerpm)
        if m:
            orig_prefix = m.group(1)

        m = re.match('(.*)-%s-%s' % (new_pkgobject.version, new_pkgobject.release),\
            new_pkgobject.sourcerpm)
        if m:
            new_prefix = m.group(1)

        # don't remove pkgs that rely on orig_pkg (yum tries to remove them)
        for pkg in base.rpmdb:
            for req in pkg.requires_names:
                if req in deps_to_resolve:
                    if pkg not in pkgs_to_not_remove and pkg not in pkgs_to_remove:
                        pkgs_to_not_remove.append(pkg)

        # determine all new_pkg subpackages that provide missing deps
        providers = {}
        for pkg in base.pkgSack:
            if pkg.sourcerpm == new_pkgobject.sourcerpm:
                pkgs_with_same_srpm.append(pkg)
                for dep in pkg.provides_names:
                    if dep in deps_to_resolve:
                        if pkg not in pkgs_to_remove:
                            
                            # build a list of all packages matching provides
                            if not providers.has_key(dep):
                                providers[dep] = []
                            providers[dep].append(pkg)

        # We now have a complete list of package providers we care about
        if providers:
            resolved = False
            for key, pkgs in providers.items():
                if len(pkgs) == 1:
                    pkgs_to_install.append(pkgs[0])
                    deps_to_resolve.remove(key)
                    resolved = True

                elif len(pkgs) > 1:
                    # Attempt to auto resolve multiple provides
                    for rpkg in pkgs_to_remove:
                        npkg = rpkg.name.replace(orig_prefix, new_prefix)
                        for pkg in pkgs:
                            if npkg == pkg.name:
                                pkgs_to_install.append(pkg)
                                resolved = True

                    # we've completed our auto resolve,
                    # if resolved lets remove the key
                    if resolved:
                        deps_to_resolve.remove(key)

                    if not resolved:
                        print '\nWARNING: Multiple Providers found for %s' % key
                        print "  %s" % [str(i) for i in pkgs]

                # remove the dep from dict since it should be handled.
                del(providers[key])

        # This is messy: determine if any of the pkgs_to_not_remove have
        # counterparts as part of same 'base name' set (but different srpm, i.e. 
        # php and php-pear has different source rpms but you want phpXY-pear too).
        while pkgs_to_not_remove:
            pkg = pkgs_to_not_remove.pop()
            m = re.match('%s-(.*)' % orig_prefix, pkg.name)
            if not m:
                continue
            replace_name = "%s-%s" % (new_prefix, m.group(1))
            for pkg2 in base.pkgSack: 
                if pkg2.name == replace_name:
                    if pkg not in pkgs_to_remove:
                        pkgs_to_remove.append(pkg)
                        if pkg in pkgs_to_not_remove:
                            pkgs_to_not_remove.remove(pkg)
                    if pkg2 not in pkgs_to_install:
                        pkgs_to_install.append(pkg2)
                        if pkg2 in pkgs_to_not_remove:
                            pkgs_to_not_remove.remove(pkg2)

        # clean up duplicates (multiple versions)
        _pkgs_to_install = []
        for pkg in pkgs_to_install:
            latest_pkg = base.pkgSack.returnNewestByName(pkg.name)[0]
            if latest_pkg not in _pkgs_to_install:
                _pkgs_to_install.append(latest_pkg)
        pkgs_to_install = _pkgs_to_install

        # Its common that newer/replacement packages won't provide all the same things.
        # Give the user the chance to bail if they are scared.
        if len(deps_to_resolve) > 0:
            print
            print "WARNING: Unable to resolve all providers: %s" % deps_to_resolve
            print
            if not opts.assumeyes:
                res = raw_input("This may be normal depending on the package.  Continue? [y/N] ")
                if not res.strip('\n').lower() in ['y', 'yes']:
                    sys.exit(1)
        
        # remove old packages
        for pkg in pkgs_to_remove:
            base.remove(pkg)
        # install new/replacement packages
        for pkg in pkgs_to_install:
            base.install(pkg) 

        return 2, ["Run transaction to replace '%s' with '%s'" % (orig_pkg, new_pkg)]

