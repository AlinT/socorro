import datetime
import logging

import socorro.lib.util as util
import socorro.webapi.rest_api_base as rstapi
import socorro.database.database as db
import socorro.lib.datetimeutil as dtutil

logger = logging.getLogger("webapi")

#=================================================================================================================
class EmailCampaignVolumeService(rstapi.JsonServiceBase):
  """ Hoopsnake API which estimates the total volume of emails
      a given campaign will generate. A campaign is based on:
      * Product
      * Crash Signature
      * Date Range

      The API returns a raw number
  """
  #-----------------------------------------------------------------------------------------------------------------
  def __init__(self, configContext):
    super(EmailCampaignVolumeService, self).__init__(configContext)
    self.database = db.Database(configContext)

  #-----------------------------------------------------------------------------------------------------------------
  # curl http://localhost:8085/201103/emailcampaigns/volume/p/Firefox/v/4.0b6/sig/js_FinishSharingTitle/start/2010-06-05/end/2010-06-13
  "/201103/emailcampaigns/volume/p/{product}/v/{versions}/sig/{signature}/start/{start_date}/end/{end_date}"
  uri = '/201103/emailcampaigns/volume/p/(.*)/v/(.*)/sig/(.*)/start/(.*)/end/(.*)'

  #-----------------------------------------------------------------------------------------------------------------
  def get(self, *args):
    " Webpy method receives inputs from uri "
    stringListFromCSV = lambda s: tuple([x.strip() for x in s.split(',')])
    convertedArgs = webapi.typeConversion([str, stringListFromCSV, str, dtutil.datetimeFromISOdateString, dtutil.datetimeFromISOdateString], args)
    parameters = util.DotDict(zip(['product', 'versions', 'signature', 'start_date', 'end_date'], convertedArgs))

    connection = self.database.connection()
    try:
      return {'emails': self.estimate_campaign_volume(connection, parameters)}
    finally:
      connection.close()

  #-----------------------------------------------------------------------------------------------------------------
  def estimate_campaign_volume(self, connection, parameters):
    " Queries reports tables for a count of unique email addresses "

    # Yeah, it isn't a half day or anything like that -- lumbergh
    # start date at 00:00:00 and end date at 23:59:59
    end_date = parameters['end_date']
    parameters['end_date'] = datetime.datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59)

    parameters['version_clause'] = ''
    if len(parameters['versions']) > 0:
      parameters['version_clause'] = " version IN %(versions)s AND "

    sql = """
        SELECT count(distinct email) as total FROM reports
        WHERE TIMESTAMP WITHOUT TIME ZONE '%(start_date)s' <= reports.date_processed AND
              TIMESTAMP WITHOUT TIME ZONE '%(end_date)s' > reports.date_processed AND
              product = %%(product)s AND
              %(version_clause)s
              signature = %%(signature)s AND
              email IS NOT NULL AND
              email ~ '.*@.*\.[a-zA-Z]{2,4}';
    """ % parameters
    cursor = connection.cursor()
    #logger.info(cursor.mogrify(sql, parameters))
    cursor.execute(sql, parameters)
    return cursor.fetchone()[0]
