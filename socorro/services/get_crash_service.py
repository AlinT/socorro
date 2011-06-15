import datetime as dt
import urllib2 as u2
import logging
logger = logging.getLogger("webapi")

import socorro.lib.util as util
import socorro.webapi.rest_api_base as rstapi
import socorro.database.database as db
import socorro.lib.datetimeutil as dtutil
import socorro.storage.crashstorage as cs

datatype_options = ('meta', 'raw_crash', 'processed')
crashStorageFunctions = ('get_meta', 'get_raw_dump', 'get_processed')
datatype_function_associations = dict(zip(datatype_options, crashStorageFunctions))

class NotADataTypeOption(Exception):
  def __init__(self, reason):
    #super(NotADataTypeOption, self).__init__("%s must be one of %s" % (reason, ','.join(datatype_options))
    Exception.__init__("%s must be one of %s" % (reason, ','.join(datatype_options)))

def dataTypeOptions(x):
  if x in datatype_options:
    return x
  raise NotADataTypeOption(x)

#=================================================================================================================
class GetCrashService(rstapi.JsonServiceBase):
  #-----------------------------------------------------------------------------------------------------------------
  def __init__(self, configContext):
    super(GetCrashService, self).__init__(configContext)
    logger.debug('GetCrash __init__')
  #-----------------------------------------------------------------------------------------------------------------
  uri = '/201005/crash/(.*)/by/uuid/(.*)'
  #-----------------------------------------------------------------------------------------------------------------
  def get(self, *args):
    convertedArgs = rstapi.typeConversion([dataTypeOptions,str], args)
    parameters = util.DotDict(zip(['datatype','uuid'], convertedArgs))
    logger.debug("GetCrash get %s", parameters)
    crashStorage = self.crashStoragePool.crashStorage()
    function_name = datatype_function_associations[parameters.datatype]
    function = crashStorage.__getattribute__(function_name)
    if function_name == 'get_raw_dump':
      return(function(parameters.uuid), "application/octet-stream")
    return function(parameters.uuid)

