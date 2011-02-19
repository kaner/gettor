#!/usr/bin/python2.5
'''
 Copyright (c) 2008, Jacob Appelbaum <jacob@appelbaum.net>, 
                     Christian Fromme <kaner@strace.org>

 This is Free Software. See LICENSE for license information.
'''
"""This library implements all of the black listing features needed for gettor.
Basically, it offers creation, removal and lookup of email addresses stored as
SHA1 hashes in a dedicated directory on the filesystem.
"""

import hashlib
import os
import re
import glob
import gettor.config
import gettor.gtlog
import gettor.utils

log = gettor.gtlog.getLogger()

class BWList:
    def __init__(self, blacklistDir):
        """A blacklist lives as hash files inside a directory and is simply a 
           number of files that represent hashed email addresses.
        """
        self.blacklistDir = blacklistDir
        # "general" is the main blacklist
        self.createSublist("general")

    def createSublist(self, blacklistName):
        """Create a sub blacklist. A blacklist is built of several sublists, 
           each for a certain purpose. There are blacklists for many 
           different types of mail. Users get blacklisted for package sending
           after they received a package for 7 days, for example.
        """
        fullDir = os.path.join(self.blacklistDir, blacklistName)
        if not os.path.isdir(fullDir):
            if not gettor.utils.createDir(fullDir):
                # XXX Change this to something more appropriate
                raise IOError("Bad dir: %s" % fullDir)

    def lookupListEntry(self, address, blacklistName="*"):
        """Check to see if we have a list entry for the given address.
        """
        if address is None:
           log.error("Argument 'address' is None")
           return False
        hashString = self.getHash(address)
        globPath = os.path.join(self.blacklistDir, blacklistName)
        hashVec = glob.glob(os.path.join(globPath, hashString))
        if len(hashVec) > 0:
            return True
        return False

    def createListEntry(self, address, blacklistName="general"):
        """Create a black- or whitelist entry
        """
        if address is None or blacklistName is None:
           log.error("Bad args in createListEntry()")
           return False
        if self.lookupListEntry(address) == False:
            hashString = self.getHash(address)
            entry = os.path.join(self.blacklistDir, blacklistName, hashString)
            try:
                fd = open(entry, 'w')
                fd.close
                return True
            except:
                log.error("Creating list entry %s failed." % entry)
                return False
        else:
            # List entry already exists
            return False

    def removeListEntry(self, address, blacklistName="*"):
        """Remove an entry from the black- or whitelist
        """
        if address is None:
           log.error("Argument 'address' is None")
           return False
        hashString = self.getHash(address)
        globPath = os.path.join(self.blacklistDir, blacklistName)
        hashVec = glob.glob(os.path.join(globPath, hashString))
        for entry in hashVec:
            try:
                log.info("Unlinking %s" % entry)
                os.unlink(entry)
            except OSError:
                log.error("Could not unlink entry %s" % entry)
                continue
        else:
            log.info("Requested removal of non-existing entry. Abord.")
            return False

    def removeAll(self, olderThanDays=0):
        """Remove all blacklist entries that are older than 'olderThanDays'
           days.
        """
        for root, dirs, files in os.walk(self.blacklistDir):
            for file in files:
                rmfile = os.path.join(root, file)
                # Only remove files older than 'olderThanDays'
                if gettor.utils.fileIsOlderThan(rmfile, olderThanDays):
                    try:
                        os.remove(rmfile)
                    except OSError:
                        try:
                            os.rmdir(rmfile)
                        except:
                            log.error("Could not remove %s." % rmfile)
                            return False
                    except:
                        log.error("Could not remove %s." % rmfile)
                        return False
        return True

    def stripEmail(self, address):
        """Strip "Bart Foobar <bart@foobar.net>" to "<bart@foobar.net">
        """
        match = re.search('<.*?>', address)
        if match is not None:
            return match.group()
        # Make sure to return the address in the form of '<bla@foo.de>'
        return gettor.utils.normalizeAddress(address)

    def getHash(self, address):
        """Return hash for a given emailaddress
        """
        emailonly = self.stripEmail(address)
        return str(hashlib.sha1(emailonly).hexdigest())

