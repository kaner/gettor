# Copyright (c) 2008 - 2011, Jacob Appelbaum <jacob@appelbaum.net>, 
#                            Christian Fromme <kaner@strace.org>
#  This is Free Software. See LICENSE for license information.

import re
import logging 

def doFilter(reqInfo):
    """DOCDOC
    """
    reqInfo['package'] = doPackageHacks(reqInfo['package'], reqInfo['locale']) 
    reqInfo['valid'] = checkAddressHack(reqInfo['user'])

    return reqInfo

def doPackageHacks(packageName, locale):
    """If someone wants one of the localizable packages, add language 
       suffix. This isn't nice because we're hard-coding package names here
       Attention: This needs to correspond to the  packages in packages.py
    """
    if packageName == "tor-browser-bundle" \
           or packageName == "tor-im-browser-bundle" \
           or packageName == "linux-browser-bundle-i386" \
           or packageName == "linux-browser-bundle-x86_64":
        # "tor-browser-bundle" => "tor-browser-bundle_de"
        packageName += "_" + locale

    return packageName

def checkAddressHack(userAddress):
    """This makes it possible to add hardcoded blacklist entries *ugh*
       XXX: This should merge somehow with the GetTor blacklisting
            mechanism at some point
    """
    logging.debug("Checking user address %s.." % userAddress)
    if re.compile(".*@.*torproject.org.*").match(userAddress):
        return False
        
    # Make sure we drop bounce mails
    if userAddress == "<>":
        logging.debug("We've received a bounce")
        return False

    # User address looks good.
    return True
