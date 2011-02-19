#!/usr/bin/python2.5
# -*- coding: utf-8 -*-
"""
 Copyright (c) 2008, Jacob Appelbaum <jacob@appelbaum.net>, 
                     Christian Fromme <kaner@strace.org>

 This is Free Software. See LICENSE for license information.

 This library implements all of the email replying features needed for gettor. 
"""

import os
import re
import sys
import smtplib
import gettext
from email import encoders
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText

import gettor.gtlog
import gettor.blacklist

__all__ = ["Response"]

log = gettor.gtlog.getLogger()

trans = None

def sendNotification(config, sendFr, sendTo):
    """Send notification to user
    """
    response = Response(config, sendFr, sendTo, None, "", False, True, "")
    message = gettor.constants.mailfailmsg
    return response.sendGenericMessage(message)

class Response:
    def __init__(self, config, reqval):
        """Intialize the reply class. The most important values are passed in
           via the 'reqval' RequestValue class. Initialize the locale subsystem
           and do early blacklist checks of reply-to addresses 
        """
        self.config = config
        self.reqval = reqval
        # Set default From: field for reply. Defaults to gettor@torproject.org
        if reqval.toField is None:
            self.srcEmail = config.getDefaultFrom()
        else:
            self.srcEmail = reqval.toField
        self.replyTo = reqval.replyTo
        # Make sure we know who to reply to. If not, we can't continue   
        assert self.replyTo is not None, "Empty reply address."
        # Set default lang in none is set. Defaults to 'en'
        if reqval.lang is None:
            reqval.lang = config.getLocale()
        self.mailLang = reqval.lang
        self.package = reqval.pack
        self.splitsend = reqval.split
        self.signature = reqval.sign
        self.cmdAddr = reqval.cmdAddr
        # If cmdAddr is set, we are forwarding mail rather than sending a 
        # reply to someone
        if self.cmdAddr is not None:
            self.sendTo = self.cmdAddr
        else:
            self.sendTo = self.replyTo

        # Initialize the reply language usage
        try:
            localeDir = config.getLocaleDir()
            trans = gettext.translation("gettor", localeDir, [reqval.lang])
            trans.install()
            # OMG TEH HACK!! Constants need to be imported *after* we've 
            # initialized the locale/gettext subsystem
            import gettor.constants
        except IOError:
            log.error("Translation fail. Trying running with -r.")
            raise

        # Init black & whitelists
        self.whiteList = gettor.blacklist.BWList(config.getWlStateDir())
        self.blackList = gettor.blacklist.BWList(config.getBlStateDir())
        # Check blacklist section 'general' list & Drop if necessary
        # XXX: This should learn wildcards
        blacklisted = self.blackList.lookupListEntry(self.replyTo, "general")
        assert blacklisted is not True, \
            "Mail from blacklisted user %s" % self.replyTo 

    def sendReply(self):
        """All routing decisions take place here. Sending of mails takes place
           here, too.
        """
        if self.isAllowed():
            # Ok, see what we've got here.
            # Was this a GetTor control command wanting us to forward a package?
            if self.cmdAddr is not None:
                success = self.sendPackage()
                if not success:
                    log.error("Failed to forward mail to '%s'" % self.cmdAddr)
                return self.sendForwardReply(success)
                
            # Did the user choose a package?
            if self.package is None:
                return self.sendPackageHelp()
            delayAlert = self.config.getDelayAlert()
            # Be a polite bot and send message that mail is on the way
            if delayAlert:
                if not self.sendDelayAlert():
                    log.error("Failed to sent delay alert.")
            # Did the user request a split or normal package download?
            if self.splitsend:
                return self.sendSplitPackage()
            else:
                return self.sendPackage()

    def isAllowed(self):
        """Do all checks necessary to decide whether the reply-to user is 
           allowed to get a reply by us.
        """
        # Check we're happy with sending this user a package
        # XXX This is currently useless since we set self.signature = True
        if not self.signature and not self.cmdAddr \
           and not self.whiteList.lookupListEntry(self.replyTo) \
           and not re.compile(".*@yahoo.com.cn").match(self.replyTo) \
           and not re.compile(".*@yahoo.cn").match(self.replyTo) \
           and not re.compile(".*@gmail.com").match(self.replyTo):
            blackListed = self.blackList.lookupListEntry(self.replyTo)
            if blackListed:
                log.info("Unsigned messaged to gettor by blacklisted user dropped.")
                return False
            else:
                # Reply with some help and bail out
                self.blackList.createListEntry(self.replyTo)
                log.info("Unsigned messaged to gettor. We will issue help.")
                return self.sendHelp()
        else:
            return True

    def isBlacklistedForMessageType(self, fname):
        """This routine takes care that for each function fname, a given user
           can access it only once. The 'fname' parameter carries the message
           type name we're looking for
        """
        # First of all, check if user is whitelisted: Whitelist beats Blacklist
        if self.whiteList.lookupListEntry(self.replyTo, "general"):
            log.info("Whitelisted user " + self.replyTo)
            return False
        # Create a unique dir name for the requested routine
        blackList = gettor.blacklist.BWList(self.config.getBlStateDir())
        blackList.createSublist(fname)
        if blackList.lookupListEntry(self.replyTo, fname):
            log.info("User " + self.replyTo + " is blacklisted for " + fname)
            return True
        else:
            blackList.createListEntry(self.replyTo, fname)
            return False

    def sendPackage(self):
        """ Send a message with an attachment to the user. The attachment is 
            chosen automatically from the selected self.package
        """
        if self.isBlacklistedForMessageType("sendPackage"):
            # Don't send anything
            return False
        log.info("Sending out %s to %s." % (self.package, self.sendTo))
        packages = gettor.packages.Packages(self.config)
        packageList = packages.getPackageList()
        filename = packageList[self.package]
        message = gettor.constants.packagemsg
        package = self.constructMessage(message, fileName=filename)
        try:
            status = self.sendMessage(package)
        except:
            log.error("Could not send package to user")
            status = False

        log.info("Send status: %s" % status)
        return status

    def sendSplitPackage(self):
        """Send a number of messages with attachments to the user. The number
           depends on the number of parts of the package.
        """
        if self.isBlacklistedForMessageType("sendSplitPackage"):
            # Don't send anything
            return False
        splitpack = self.package + ".split"
        splitdir = os.path.join(self.config.getPackDir(), splitpack)
        try:
            entry = os.stat(splitdir)
        except OSError, e:
            log.error("Not a valid directory: %s" % splitdir)
            return False
        files = os.listdir(splitdir)
        # Sort the files, so we can send 01 before 02 and so on..
        files.sort()
        nFiles = len(files)
        num = 0
        # For each available split file, send a mail
        for filename in files:
            fullPath = os.path.join(splitdir, filename)
            num = num + 1
            subj = "[GetTor] Split package [%02d / %02d] " % (num, nFiles) 
            message = gettor.constants.splitpackagemsg
            package = self.constructMessage(message, subj, fullPath)
            try:
                status = self.sendMessage(package)
                log.info("Sent out split package [%02d / %02d]. Status: %s" \
                        % (num, nFiles, status))
            except:
                log.error("Could not send package %s to user" % filename)
                # XXX What now? Keep on sending? Bail out? Use might have 
                # already received 10 out of 12 packages..
                status = False

        return status

    def sendDelayAlert(self):
        """Send a polite delay notification
        """
        if self.isBlacklistedForMessageType("sendDelayAlert"):
            # Don't send anything
            return False
        log.info("Sending delay alert to %s" % self.sendTo)
        return self.sendGenericMessage(gettor.constants.delayalertmsg)
            
    def sendHelp(self):
        """Send a help mail. This happens when a user sent us a request we 
           didn't really understand
        """
        if self.isBlacklistedForMessageType("sendHelp"):
            # Don't send anything
            return False
        log.info("Sending out help message to %s" % self.sendTo)
        return self.sendGenericMessage(gettor.constants.helpmsg)

## XXX the following line was used below to automatically list the names
## of available packages. But they were being named in an arbitrary
## order, which caused people to always pick the first one. I listed
## tor-browser-bundle first since that's the one they should want.
## Somebody should figure out how to automate yet sort. -RD
##    """ + "".join([ "\t%s\n" % key for key in packageList.keys()]) + """

    def sendPackageHelp(self):
        """Send a helpful message to the user interacting with us about
           how to select a proper package
        """
        if self.isBlacklistedForMessageType("sendPackageHelp"):
            # Don't send anything
            return False
        log.info("Sending package help to %s" % self.sendTo)
        return self.sendGenericMessage(gettor.constants.multilangpackagehelpmsg)

    def sendForwardReply(self, status):
        """Send a message to the user that issued the forward command
        """
        log.info("Sending reply to forwarder '%s'" % self.replyTo)
        message = "Forwarding mail to '%s' status: %s" % (self.sendTo, status)
        # Magic: We're now returning to the original issuer
        self.sendTo = self.replyTo
        return self.sendGenericMessage(message)

    def sendGenericMessage(self, text):
        """Generic message sending routine. All mails that are being sent out
           go through this function.
        """
        message = self.constructMessage(text)
        try:
            status = self.sendMessage(message)
        except:
            log.error("Could not send message to user %s" % self.sendTo)
            status = False

        log.info("Send status: %s" % status)
        return status

    def constructMessage(self, messageText, subj="[GetTor] Your Request", fileName=None):
        """Construct a multi-part mime message, including only the first part
           with plaintext.
        """

        message = MIMEMultipart()
        message['Subject'] = subj
        message['To'] = self.sendTo
        message['From'] = self.srcEmail
        
        text = MIMEText(messageText, _subtype="plain", _charset="utf-8")
        # Add text part
        message.attach(text)

        # Add a file part only if we have one
        if fileName:
            filePart = MIMEBase("application", "zip")
            fp = open(fileName, 'rb')
            filePart.set_payload(fp.read())
            fp.close()
            encoders.encode_base64(filePart)
            # Add file part
            filePart.add_header('Content-Disposition', 'attachment', filename=os.path.basename(fileName))
            message.attach(filePart)

        return message

    def sendMessage(self, message, smtpserver="localhost:25"):
        """Send out message via STMP. If an error happens, be verbose about 
           the reason
        """
        try:
            smtp = smtplib.SMTP(smtpserver)
            smtp.sendmail(self.srcEmail, self.sendTo, message.as_string())
            smtp.quit()
            status = True
        except smtplib.SMTPAuthenticationError:
            log.error("SMTP authentication error")
            return False
        except smtplib.SMTPHeloError:
            log.error("SMTP HELO error")
            return False
        except smtplib.SMTPConnectError:
            log.error("SMTP connection error")
            return False
        except smtplib.SMTPDataError:
            log.error("SMTP data error")
            return False
        except smtplib.SMTPRecipientsRefused:
            log.error("SMTP refused to send to recipients")
            return False
        except smtplib.SMTPSenderRefused:
            log.error("SMTP sender address refused")
            return False
        except smtplib.SMTPResponseException:
            log.error("SMTP response exception received")
            return False
        except smtplib.SMTPServerDisconnected:
            log.error("SMTP server disconnect exception received")
            return False
        except smtplib.SMTPException:
            log.error("General SMTP error caught")
            return False
        except Exception, e:
            log.error("Unknown SMTP error while trying to send via local MTA")
            log.error("Here is the exception I saw: %s" % sys.exc_info()[0])
            log.error("Detail: %s" %e)

            return False

        return status
