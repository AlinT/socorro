#
# collect.py, collector functions for Pylons, CGI, and mod_python collectors
#

import os, cgi, sys, uuid, tempfile, simplejson
from datetime import datetime
from time import time
import re
import config
import random

compiledRegularExpressionType = type(re.compile(''))
functionType = type(lambda x: x)

def regexpHandlerFactory(regexp):
  def egexpHandler(x):
    return regexp.search(x)
  return egexpHandler

def boolHandlerFactory(aBool):
  def boolHandler(dummy):
    return aBool
  return boolHandler

def genericHandlerFactor(anObject):
  def genericHandler(x):
    return anObject == x
  return genericHandler

def preprocessThrottleConditions(originalThrottleConditions):
  newThrottleConditions = []
  for key, condition, percentage in originalThrottleConditions:
    #print "preprocessing %s %s %d" % (key, condition, percentage)
    conditionType = type(condition)
    if conditionType == compiledRegularExpressionType:
      #print "reg exp"
      newCondition = regexpHandlerFactory(condition)
      #print newCondition
    elif conditionType == bool:
      #print "bool"
      newCondition = boolHandlerFactory(condition)
      #print newCondition
    elif conditionType == functionType:
      newCondition = condition
    else:
      newCondition = genericHandlerFactor(condition)
    newThrottleConditions.append((key, newCondition, percentage))
  return newThrottleConditions

processedThrottleConditions = preprocessThrottleConditions(config.throttleConditions)

def throttle (json):
  #print processedThrottleConditions
  for key, condition, percentage in processedThrottleConditions:
    #print "testing  %s %s %d" % (key, condition, percentage)
    try:
      throttleMatch = condition(json[key])
    except KeyError:
      if key == None:
        throttleMatch = condition(None)
      else:
        #print "bad key"
        continue
    if throttleMatch:
      randint = random.randint(0, 100)
      #print "throttle: %d %d %s" % (randint, percentage, randint > percentage)
      return randint > percentage
  return True


def mkdir(path):
  """Make a directory, using the permissions and GID specified in the config"""
  os.mkdir(path, config.dirPermissions)
  # The umask of the apache process is typically 022. That's not good enough,
  # and we don't want to mess with the whole process, so we set the permissions
  # explicitly.
  os.chmod(path, config.dirPermissions)
  if config.dumpGID is not None:
    os.chown(path, -1, config.dumpGID)

def makedirs(path):
  head, tail = os.path.split(path)
  if not tail:
    head, tail = os.path.split(head)
  if head and tail and not os.path.exists(head):
    makedirs(head)
    if tail == os.curdir:
      return
  mkdir(path)

def ensureDiskSpace():
  pass

def checkDumpQueue():
  pass

def backOffMessage():
  pass

def makeDumpDir(base):
  """Create a directory to hold a group of dumps, and set permissions"""
  tmpPath = tempfile.mkdtemp(dir=base, prefix=config.dumpDirPrefix)
  os.chmod(tmpPath, config.dirPermissions)
  if config.dumpGID is not None:
    os.chown(tmpPath, -1, config.dumpGID)
  return tmpPath


def findLastModifiedDirInPath(path):
  names = os.listdir(path)
  breakpadDirs = [os.path.join(path, entry) for entry
                  in names if entry.startswith(config.dumpDirPrefix)]

  # This could happen if some other process or person has removed things
  # from our dated paths
  if len(breakpadDirs) == 0:
    return makeDumpDir(datePath)

  # Find the newest directory
  mtimeList = [(os.stat(path).st_mtime, fullpath) for fullpath in breakpadDirs
               if os.path.isdir(fullpath)]
  mtimeList.sort()
  latestDir = mtimeList[-1][1]
  return latestDir


#
# This will create date-partitioned paths, which the processor cronjob
# will come through and clean up in an os.walk() function.
#
# Example file stored on March 18th 2007, between 2 and 3 pm:
#
# /base/2007/03/18/14/bp_qew2f3/022c9812-bb4d-43cb-bf90-26b11f5a75d9.dump
#
# If the "bp_qew2f3" directory gets too full, another directory will
# be created by tempfile.mkdtemp, and eventually the code will move on
# to another hourly directory.
#
def getParentPathForDump(storageRoot):
  """Return a directory path to hold dump data, creating if necessary"""
  # First make an hourly directory if necessary
  utc = datetime.utcnow()
  dateString = "%04u-%02u-%02u-%02u" % (utc.year, utc.month, utc.day, utc.hour)
  datePath = os.path.join(storageRoot, str(utc.year), str(utc.month),
                          str(utc.day), str(utc.hour))

  # if it's not there yet, create the date directory and its first
  # dump directory
  if not os.path.exists(datePath):
    makedirs(datePath)
    return (makeDumpDir(datePath), dateString)

  # return the last-modified dir if it has less than dumpCount entries,
  # otherwise make a new one
  latestDir = findLastModifiedDirInPath(datePath)
  if len(os.listdir(latestDir)) >= config.dumpDirCount:
    return (makeDumpDir(datePath), dateString)

  return (latestDir, dateString)

def openFileForDumpID(dumpID, dumpDir, suffix, mode):
  filename = os.path.join(dumpDir, dumpID + suffix)
  outfile = open(filename, mode)

  if config.dumpGID is not None:
    os.chown(filename, -1, config.dumpGID)
  os.chmod(filename, config.dumpPermissions)

  return outfile

def storeDump(dumpfile, storageRoot):
  """Stream the uploaded dump to a file, and store accompanying metadata.
  Returns (dumpID, dumpPath, dateString)"""
  (dirPath, dateString) = getParentPathForDump(storageRoot)
  dumpID = str(uuid.uuid1())
  outfile = openFileForDumpID(dumpID, dirPath, config.dumpFileSuffix, 'wb')

  # XXXsayrer need to peek at the first couple bytes for a sanity check
  # breakpad leading bytes: 0x504d444d
  #
  try:
    while 1:
      data = dumpfile.read(4096)
      if not data:
        break
      outfile.write(data)
  finally:
    outfile.close()

  return (dumpID, dirPath, dateString)

def doCreateSymbolicLink(targetPathname, linkPathname):
  """ Create a symbolic link called 'linkPathname' linked to 'targetPathname'"""
  os.symlink(targetPathname, linkPathname)
  os.chmod(linkPathname, config.dirPermissions)
  if config.dumpGID is not None:
    os.chown(linkPathname, -1, config.dumpGID)

def createSymbolicLinkForIndex(id, path, suffix, storageRoot):
  """ For each json file stored, we're going to save a symbolic link to that file in a directory of the form:
        {storageRoot}/index/{hostname}/{jsonfile}.symlink  We can access this structure faster than
        the distributed structure where the actual json and dump files live.
  """
  # create path for index link
  indexLinkPath = os.path.join(storageRoot, "index", os.uname()[1])
  # create relative path for the link target
  targetRelativePathName = os.path.join("../..", path[len(storageRoot) + 1:], "%s%s" % (id, suffix))
  try:
    # create symbolic link
    symbolicLinkPathname = os.path.join(indexLinkPath, "%s%s" % (id, ".symlink"))
    doCreateSymbolicLink(targetRelativePathName, symbolicLinkPathname)
  except OSError:
    # {hostname} directory does not exist
    try:
      mkdir(indexLinkPath)
    except OSError:
      # "index" directory probably doesn't exist - create it
      mkdir(os.path.join(storageRoot, "index"))
      # retry creation of {hostname} directory
      mkdir(indexLinkPath)
    # retry creation of symbolic link
    doCreateSymbolicLink(targetRelativePathName, symbolicLinkPathname)

def createSymbolicLinkForIndexWithSubdirectories(id, path, suffix, storageRoot):
  """ For each json file stored, we're going to save a symbolic link to that file in a directory of the form:
        {storageRoot}/index/{hostname}/{YYYMMDD}/{jsonfile}.symlink  We can access this structure faster than
        the distributed structure where the actual json and dump files live.
  """
  # create path for index link
  now = datetime.now()
  indexLinkPath = os.path.join(storageRoot, "index", os.uname()[1], "%04d%02d%02d" % (now.year, now.month, now.day))
  # create relative path for the link target
  targetRelativePathName = os.path.join("../../..", path[len(storageRoot) + 1:], "%s%s" % (id, suffix))
  try:
    # create symbolic link
    symbolicLinkPathname = os.path.join(indexLinkPath, "%s%s" % (id, ".symlink"))
    doCreateSymbolicLink(targetRelativePathName, symbolicLinkPathname)
  except OSError:
    # {hostname} or {YYYYMMDD} directory does not exist
    makedirs(indexLinkPath)
    # retry creation of symbolic link
    doCreateSymbolicLink(targetRelativePathName, symbolicLinkPathname)

def createJSON(form):
  names = [name for name in form.keys() if name != config.dumpField]
  fields = {}
  for name in names:
    if type(form[name]) == type(""):
      fields[name] = form[name]
    else:
      fields[name] = form[name].value
  fields["timestamp"] = time()
  return fields

def storeJSON(dumpID, dumpDir, fields, storageRoot, useIndexSubdirectories):
  outfile = openFileForDumpID(dumpID, dumpDir, config.jsonFileSuffix, 'w')
  try:
    simplejson.dump(fields, outfile)
  finally:
    outfile.close()
  # create index symbolic link for this json file
  if useIndexSubdirectories:
    createSymbolicLinkForIndexWithSubdirectories(dumpID, dumpDir, config.jsonFileSuffix, storageRoot)
  else:
    createSymbolicLinkForIndex(dumpID, dumpDir, config.jsonFileSuffix, storageRoot)


def makeResponseForClient(dumpID, dateString):
  response = "CrashID=%s%s\n" % (config.dumpIDPrefix, dumpID)
  if config.reporterURL is not None:
    response += "ViewURL=%s/report/index/%s?date=%s\n" % (config.reporterURL,
                                                          dumpID,
                                                          dateString)
  return response