#!/usr/bin/python2.5
# -*- coding: utf-8 -*-
"""
  Copyright (c) 2008, Jacob Appelbaum <jacob@appelbaum.net>, 
                     Christian Fromme <kaner@strace.org>

 This is Free Software. See LICENSE for license information.

 This library implements all of the email parsing features needed for gettor.
"""

import sys
import email
import dkim
import re

import gettor.gtlog
import gettor.packages

__all__ = ["requestMail"]

log = gettor.gtlog.getLogger()

class RequestVal:
    """A simple value class carrying everything that is interesting from a
       parsed email
       toField  - Who this mail was sent to
       replyTo  - Who sent us the mail, this is also who gets the reply
       lang     - The language the user wants the reply in
       split    - True if the user wants us to send Tor in split files
       sign     - True if that mail carried a good DKIM signature
       cmdAddr  - Special commands from the GetTor admin
    """
    def __init__(self, toField, replyTo, lang, pack, split, sign, cmdAddr):
        self.toField = toField
        self.replyTo = replyTo
        self.lang = lang
        self.pack = pack
        self.split = split
        self.sign = sign
        self.cmdAddr = cmdAddr
    
class requestMail:
    defaultLang = "en"
    # XXX Move this to the config file
    #                  LANG: ALIASE
    supportedLangs = { "en": ("english", ),
                       "fa": ("farsi", ),
                       "de": ("deutsch", ),
                       "ar": ("arabic", ),
                       "es": ("spanish", ),
                       "fr": ("french", ),
                       "it": ("italian", ),
                       "nl": ("dutch", ),
                       "pl": ("polish", ),
                       "ru": ("russian", ),
                       "zh_CN": ("chinese", "zh",) }

    def __init__(self, config):
        """ Read message from stdin, initialize and do some early filtering and
            sanitization
        """
        # Read email from stdin
        self.rawMessage = sys.stdin.read()
        self.parsedMessage = email.message_from_string(self.rawMessage)

        # WARNING WARNING *** This next line whitelists all addresses
        #                 *** It exists as long as we don't want to check 
        #                 *** for DKIM properly
        self.signature = True
        # WARNING WARNING ***

        self.config = config
        self.gotPlusReq = False     # Was this a gettor+lang@ request?
        self.returnPackage = None   
        self.splitDelivery = False
        self.commandAddress = None
        self.replyLocale = self.defaultLang
        self.replytoAddress = self.parsedMessage["Return-Path"]
        self.bounce = False         # Is the mail a bounce? 
        self.defaultFrom = self.config.getDefaultFrom()
        
        # Filter rough edges
        self.doEarlyFilter()
        # We want to parse, log and act on the "To" field
        self.sanitizeAndAssignToField(self.parsedMessage["to"])

        log.info("User %s made request to %s" % \
                (self.replytoAddress, self.toAddress))
        self.gotPlusReq = self.matchPlusAddress()
        packager = gettor.packages.Packages(config)
        self.packages = packager.getPackageList()
        assert len(self.packages) > 0, "Empty package list"

        # TODO XXX:
        # This should catch DNS exceptions and fail to verify if we have a 
        # dns timeout
        # We also should catch totally malformed messages here
        #try:
        #           if dkim.verify(self.rawMessage):
        #               self.signature = True
        #       except:
        #           pass

    def sanitizeAndAssignToField(self, toField):
        """Do basic santization of the To: field of the mail header
        """
        regexGettorMail = '.*(<)?(gettor.*@torproject.org)+(?(1)>).*'
        match = re.match(regexGettorMail, toField)
        if match:
            self.toAddress= match.group(2)
        else:
            # Fall back to default From: address
            self.toAddress = self.defaultFrom

    def parseMail(self):
        """Main mail parsing routine. Returns a RequestVal value class
        """
        if self.parsedMessage.is_multipart():
            for part in self.parsedMessage.walk():
                if part.get_content_maintype() == "text":
                    # We found a text part, parse it
                    self.parseTextPart(part.get_payload(decode=1))
        else:
            self.parseTextPart(self.parsedMessage.get_payload(decode=1))

        if self.returnPackage is None:
            log.info("User didn't select any packages")

        return RequestVal(self.toAddress,
                          self.replytoAddress,
                          self.replyLocale,
                          self.returnPackage,
                          self.splitDelivery,
                          self.signature,
                          self.commandAddress)

    def parseTextPart(self, text):
        """If we've found a text part in a multipart email or if we just want
           to parse a non-multipart message, this is the routine to call with
           the text body as its argument
        """
        text = self.stripTags(text)
        if not self.gotPlusReq:
            self.matchLang(text)
        self.checkLang()
    
        lines = text.split('\n')
        for line in lines:
            if self.returnPackage is None:
                self.matchPackage(line)
            if self.splitDelivery is False:
                self.matchSplit(line)
            if self.commandAddress is None:
                self.matchCommand(line)

        self.torSpecialPackageExpansion()

    def matchPlusAddress(self):
        """See whether the user sent his email to a 'plus' address, for 
           instance to gettor+fa@tpo. Plus addresses are the current 
           mechanism to set the reply language
        """
        regexPlus = '.*(<)?(\w+\+(\w+)@\w+(?:\.\w+)+)(?(1)>)'
        match = re.match(regexPlus, self.toAddress)
        if match:
            self.replyLocale = match.group(3)
            log.info("User requested language %s" % self.replyLocale)
            return True
        else:
            log.info("Not a 'plus' address")
            return False

    def matchPackage(self, line):
        """Look up which package the user wants to have"""
        for package in self.packages.keys():
            matchme = ".*" + package + ".*"
            match = re.match(matchme, line, re.DOTALL)    
            if match: 
                self.returnPackage = package
                log.info("User requested package %s" % self.returnPackage)
                return

    def matchSplit(self, line):
        """If we find 'split' somewhere we assume that the user wants a split 
           delivery
        """
        match = re.match(".*split.*", line, re.DOTALL)
        if match:
            self.splitDelivery = True
            log.info("User requested a split delivery")

    def matchLang(self, line):
        """See if we have a "Lang: <lang>" directive in the mail. If so,
           set the reply language appropriatly.
           Note that setting the language in this way is somewhat deprecated.
           Currently, replay language is chosen by the user with "plus" email
           addresses (e.g. gettor+fa@tpo)
        """
        match = re.match(".*[Ll]ang:\s+(.*)$", line, re.DOTALL)
        if match:
            self.replyLocale = match.group(1)
            log.info("User requested locale %s" % self.replyLocale)

    def matchCommand(self, line):
        """Check if we have a command from the GetTor admin in this email.
           Command lines always consists of the following syntax:
           'Command: <password> <command part 1> <command part 2>'
           For the forwarding command, part 1 is the email address of the
           recipient, part 2 is the package name of the package that needs
           to be forwarded.
           The password is checked against the password found in the file
           configured as cmdPassFile in the GetTor configuration.
        """
        match = re.match(".*[Cc]ommand:\s+(.*)$", line, re.DOTALL)
        if match:
            log.info("Command received from %s" % self.replytoAddress) 
            cmd = match.group(1).split()
            length = len(cmd)
            assert length == 3, "Wrong command syntax"
            auth = cmd[0]
            # Package is parsed by the usual package parsing mechanism
            package = cmd[1]
            address = cmd[2]
            verified = gettor.utils.verifyPassword(self.config, auth)
            assert verified == True, \
                    "Unauthorized attempt to command from: %s" \
                    % self.replytoAddress
            self.commandAddress = address

    def torSpecialPackageExpansion(self):
        """If someone wants one of the localizable packages, add language 
           suffix. This isn't nice because we're hard-coding package names here
           Attention: This needs to correspond to the  packages in packages.py
        """
        if self.returnPackage == "tor-browser-bundle" \
               or self.returnPackage == "tor-im-browser-bundle" \
               or self.returnPackage == "linux-browser-bundle-i386" \
               or self.returnPackage == "linux-browser-bundle-x86_64":
            # "tor-browser-bundle" => "tor-browser-bundle_de"
	    self.returnPackage = self.returnPackage + "_" + self.replyLocale 

    def stripTags(self, string):
        """Simple HTML stripper
        """
        return re.sub(r'<[^>]*?>', '', string)

    def getRawMessage(self):
        return self.rawMessage

    def hasVerifiedSignature(self):
        return self.signature

    def getParsedMessage(self):
        return self.parsedMessage

    def getReplyTo(self):
        return self.replytoAddress

    def getPackage(self):
        return self.returnPackage

    def getLocale(self):
        return self.replyLocale

    def getSplitDelivery(self):
        return self.splitDelivery

    def getAll(self):
        return (self.replytoAddress, self.replyLocale, \
                self.returnPackage, self.splitDelivery, self.signature)

    def checkLang(self):
        """Look through our aliases list for languages and check if the user
           requested an alias rather than an 'official' language name. If he 
           does, map back to that official name. Also, if the user didn't 
           request a language we support, fall back to default.
        """
        for (lang, aliases) in self.supportedLangs.items():
            if lang == self.replyLocale:
                log.info("User requested lang %s" % lang)
                return
            if aliases is not None:
                for alias in aliases:
                    if alias == self.replyLocale:
                        log.info("Request for %s via alias %s" % (lang, alias))
                        # Set it back to the 'official' name
                        self.replyLocale = lang
                        return
        else:
            log.info("Requested language %s not supported. Falling back to %s" \
                        % (self.replyLocale, self.defaultLang))
            self.replyLocale = self.defaultLang
            return

    def checkInternalEarlyBlacklist(self):
        """This is called by doEarlyFilter() and makes it possible to add
           hardcoded blacklist entries
           XXX: This should merge somehow with the GetTor blacklisting
                mechanism at some point
        """
        if re.compile(".*@.*torproject.org.*").match(self.replytoAddress):
            return True
        else:
            return False
            
    def doEarlyFilter(self):
        """This exists to by able to drop mails as early as possible to avoid
           mail loops and other terrible things. 
           Calls checkInternalEarlyBlacklist() to filter unwanted sender 
           addresses
        """
        # Make sure we drop bounce mails
        if self.replytoAddress == "<>":
                log.info("We've received a bounce")
                self.bounce = True
        assert self.bounce is not True, "We've got a bounce. Bye."

        # Make sure we drop stupid from addresses
        badMail = "Mail from address: %s" % self.replytoAddress
        assert self.checkInternalEarlyBlacklist() is False, badMail
