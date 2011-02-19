#!/usr/bin/python
# -*- coding: utf-8 -*-
'''
 Copyright (c) 2008, Jacob Appelbaum <jacob@appelbaum.net>, 
                     Christian Fromme <kaner@strace.org>

 This is Free Software. See LICENSE for license information.


 We grab configurable values from the users' gettor config file. If that file 
 is not present, we will supply reasonable defaults. Config files are ini-style
 formatted. We know this is ugly, but we prefer it to XML and also ConfigParser
 seems handy. ;-)

 A valid config file should look like this:
    
     [global]
     stateDir = /var/lib/gettor/
     blStateDir = /var/lib/gettor/bl/
     distDir = /var/lib/gettor/pkg/
     srcEmail = gettor@foo.org
     locale = en
     logSubSystem = nothing
     logFile = /dev/null
     localeDir = /usr/share/locale
     delayAlert = True
     cmdPassFile = /var/lib/gettor/pass
     dumpFile = /var/lib/gettor/dump
     defaultFrom = gettor@torproject.org

 Note that you can set from none to any of these values in your config file.
 Values you dont provide will be taken from the defaults in 'useConf'.

 Here is what each of them is used for individually:

 blStateDir:    Blacklisted (hashed) email addresses go here
 wlStateDir:    Whitelisted (hashed) email addresses go here
 distDir:       Sent-out Tor packages are found here
 srcEmail:      The email containing the Tor package will use this as 'From:'
 locale:        Choose your default mail and log locale
 logFile:       If 'file' logging is chosen, log to this file
 logSubSystem:  This has to be one of the following strings:
                'nothing':  Nothing is logged anywhere (Recommended)
                'stdout':   Log to stdout
                'syslog':   Logmessages will be written to syslog
                'file':     Logmessages will be written to a file (Not that 
                            this needs the 'logFile' option in the config file
                            also set to something useful
 localeDir:     This is where the 'en/LC_MESSAGES/gettor.mo' or 
                'whateverlang/LC_MESSAGES/gettor.mo' should go
 delayAlert:    If set to True (the default), a message will be sent to any
                user who has properly requested a package. The message confirms
                that a package was selected and will be sent.
 cmdPassFile:   Where our forward command password resides
 dumpFile:      Where failed mails get stored
 defaultFrom:   Use this email address in the From: field, if all else fails to
                make sense

 If no valid config file is provided to __init__, gettorConf will try to use
 '~/.gettorrc' as default config file. If that fails, the default values from
 useConf will be used.

 Run this module from the commandline to have it print a useful default config
 like so:

     $ ./gettor_config.py > ~/.gettorrc

'''

import os
import sys
import ConfigParser

__all__ = ["Config"]

class Config:
    '''
    Initialize gettor with default values if one or more values are missing 
    from the config file. This will return entirely default values if the 
    configuration file is missing. Our default file location is ~/.gettorrc 
    of $USER.
    '''

    def __init__(self, path = os.path.expanduser("~/.gettorrc")):
        """Most of the work happens here. Parse config, merge with default values,
           prepare outConf.
        """

        self.configFile = os.path.expanduser(path)

        #               Variable name   |  Default value           | Section
        self.useConf = {"stateDir":     ("/var/lib/gettor/",        "global"),
                        "blStateDir":   ("/var/lib/gettor/bl/",     "global"),
                        "wlStateDir":   ("/var/lib/gettor/wl/",     "global"),
                        "srcEmail":     ("gettor@torproject.org",   "global"),
                        "distDir":      ("/var/lib/gettor/dist/",   "global"),
                        "packDir":      ("/var/lib/gettor/pkg/",    "global"),
                        "locale":       ("en",                      "global"),
                        "logSubSystem": ("nothing",                 "global"),
                        "logFile":      ("/dev/null",               "global"),
                        "localeDir":    ("/usr/share/locale",       "global"),
                        "cmdPassFile":  ("/var/lib/gettor/cmdpass", "global"),
                        "dumpFile":     ("/var/lib/gettor/dump",    "global"),
                        "delayAlert":   (True,                      "global"),
                        "defaultFrom":  ("gettor@torproject.org",   "global")}

        # One ConfigParser instance to read the actual values from config
        self.config = ConfigParser.ConfigParser()
        # And another to provide a useable default config as output. This is
        # only because the user may have strange stuff inside his config file.
        # We're trying to be failsafe here
        self.outConf = ConfigParser.ConfigParser()

        try:
            if os.access(self.configFile, os.R_OK):
                self.config.read(self.configFile)
        except:
            pass

        # Main parser loop:
        # * Merge default values with those from the config file, if there are
        #   any
        # * Update values from config file into useConf
        # * Ignore sections and values that are not found in useConf, but in
        #   the config file (wtf?)
        # * Prepare outConf
        for dkey, (dval, sec) in self.useConf.items():
            if not self.outConf.has_section(sec):
                self.outConf.add_section(sec)
            try:
                for key, val in self.config.items(sec):
                    # Unfortunatly, keys from the config are not case-sensitive
                    if key.lower() == dkey.lower():
                        self.useConf[dkey] = val, sec
                        self.outConf.set(sec, dkey, val)
                        break
                else:
                    # Add default value for dkey
                    self.outConf.set(sec, dkey, dval)
                    
            except:
                self.outConf.set(sec, dkey, dval)

    def printConfiguration(self):
        """Print out config file. This works even if there is none
        """
        return self.outConf.write(sys.stdout)

    # All getter routines live below
    def getStateDir(self):
        return self.useConf["stateDir"][0]

    def getBlStateDir(self):
        return self.useConf["blStateDir"][0]

    def getWlStateDir(self):
        return self.useConf["wlStateDir"][0]

    def getSrcEmail(self):
        return self.useConf["srcEmail"][0]

    def getDistDir(self):
        return self.useConf["distDir"][0]

    def getPackDir(self):
        return self.useConf["packDir"][0]

    def getLocale(self):
        return self.useConf["locale"][0]

    def getLogSubSystem(self):
        return self.useConf["logSubSystem"][0]

    def getLogFile(self):
        return self.useConf["logFile"][0]

    def getLocaleDir(self):
        return self.useConf["localeDir"][0]

    def getCmdPassFile(self):
        return self.useConf["cmdPassFile"][0]

    def getDelayAlert(self):
        return self.useConf["delayAlert"][0]

    def getDumpFile(self):
        return self.useConf["dumpFile"][0]

    def getDefaultFrom(self):
        return self.useConf["defaultFrom"][0]
