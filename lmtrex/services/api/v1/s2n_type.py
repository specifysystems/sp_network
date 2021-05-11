import typing

RecordsList = typing.List[typing.Dict]

# .............................................................................
class S2nKey:
    # standard service output keys
    COUNT = 'count'
    RECORD_FORMAT = 'record_format'
    RECORDS = 'records'
    ERRORS = 'errors'
    QUERY_TERM = 'query_term'
    # output one service at a time
    SERVICE = 'service'
    PROVIDER = 'provider'
    PROVIDER_QUERY = 'provider_query'
    # other S2N constant keys
    NAME = 'name'
    # input request multiple services
    SERVICES = 'services'
    PARAM = 'param'
    OCCURRENCE_COUNT = 'gbif_occurrence_count'
    OCCURRENCE_URL = 'gbif_occurrence_url'
    
    @classmethod
    def response_keys(cls):
        return  set([
            cls.COUNT, cls.RECORD_FORMAT, cls.RECORDS, cls.ERRORS,  
            cls.QUERY_TERM, cls.SERVICE, cls.PROVIDER, cls.PROVIDER_QUERY])


# # .............................................................................
# Change to TypedDict on update to Python 3.8+
# # This corresponds to the base_response in OpenAPI specification
# class S2nOutput(typing.NamedTuple):
#     count: int
#     query_term: str
#     service: str
#     provider: str
#     provider_query: typing.List[str] = []
#     record_format: str = ''
#     records: typing.List[dict] = []
#     errors: typing.List[str] = []
#
# # .............................................................................
# def print_s2n_output(out_obj, count_only=False):
#     missing = 0
#     print('*** S^n output ***')
#     elements = {
#         'count': out_obj.count, 'provider': out_obj.provider, 
#         'errors': out_obj.errors, 'provider_query': out_obj.provider_query, 
#         'query_term': out_obj.query_term, 'records': out_obj.records }    
#     for name, attelt in elements.items():
#         try:
#             if name == 'records' and count_only is True:
#                 print('{}: {} returned records'.format(name, len(attelt)))
#             else:
#                 print('{}: {}'.format(name, attelt))
#         except:
#             missing += 1
#             print('Missing {} element'.format(name))
#     print('Missing {} elements'.format(missing))
#     print('')
     

# # .............................................................................
# class S2nOutput(dict):
#     'count': int
#     'query_term': str
#     'service': str
#     'provider': str
#     'provider_query': typing.List[str] = []
#     'record_format': str = ''
#     'records': typing.List[dict] = []
#     'errors': typing.List[str] = []
#      
#     # ...............................................
#     def __init__(
#             self, count, query_term, service, provider, provider_query=[], 
#             record_format='', records=[], errors=[]):
#         so = {
#             'count': count, 'query_term': query_term, 'service': service, 
#             'provider': provider, 'provider_query': provider_query, 
#             'record_format': record_format, 'records': records, 'errors': errors
#             }
#         return so

# .............................................................................
class S2n:
    RECORD_FORMAT = 'Lifemapper service broker schema TBD'
    
# TODO: change query_term to a list or dictionary
class S2nOutput(object):
    count: int
    query_term: str
    service: str
    provider: str
    provider_query: typing.List[str] = []
    record_format: str = ''
    records: typing.List[dict] = []
    errors: typing.List[str] = []
     
    def __init__(
            self, count, query_term, service, provider, provider_query=[], 
            record_format='', records=[], errors=[]):
        # Dictionary is json-serializable
        self._response = {
            S2nKey.COUNT: count, S2nKey.QUERY_TERM: query_term, 
            S2nKey.SERVICE: service, S2nKey.PROVIDER: provider, 
            S2nKey.PROVIDER_QUERY: provider_query, 
            S2nKey.RECORD_FORMAT: record_format, S2nKey.RECORDS: records, 
            S2nKey.ERRORS: errors}
     
    def set_value(self, prop, value):
        if prop in (
            S2nKey.COUNT, S2nKey.QUERY_TERM, S2nKey.SERVICE, S2nKey.PROVIDER, 
            S2nKey.PROVIDER_QUERY, S2nKey.RECORD_FORMAT, S2nKey.RECORDS, S2nKey.ERRORS):
            # Append or set
            self._response[prop] = value
        else:
            raise Exception('Unrecognized property {}'.format(prop))
        
    def append_value(self, prop, value):
        if prop in (S2nKey.PROVIDER_QUERY, S2nKey.RECORDS, S2nKey.ERRORS):
            # Append or set
            self._response[prop].append(value)
        else:
            raise Exception(
                'Property {} is not a multi-value element, use `set_value`'.format(prop))

    @property
    def response(self):
        return self._response
    
    @property
    def count(self):
        return self._response[S2nKey.COUNT]
  
    @property
    def query_term(self):
        return self._response[S2nKey.QUERY_TERM]
  
    @property
    def service(self):
        return self._response[S2nKey.SERVICE]
  
    @property
    def provider(self):
        return self._response[S2nKey.PROVIDER]
 
    @property
    def provider_query(self):
        return self._response[S2nKey.PROVIDER_QUERY]
  
    @property
    def record_format(self):
        return self._response[S2nKey.RECORD_FORMAT]
  
    @property
    def records(self):
        return self._response[S2nKey.RECORDS]
  
    @property
    def errors(self):
        return self._response[S2nKey.ERRORS]

# .............................................................................
class S2nError(str):
    pass


# .............................................................................
def _print_oneprov_output(oneprov, do_print_rec):
    print('* One provider S^n output *')
    for name, attelt in oneprov.items():
        try:
            if name == 'records':
                print('   records')
                if do_print_rec is False:
                    print('      {}: {} returned records'.format(name, len(attelt)))
                else:
                    for rec in attelt:
                        print('      record')
                        for k, v in rec.items():
                            print('         {}: {}'.format(k, v))
            else:
                print('   {}: {}'.format(name, attelt))
        except:
            pass

# ....................................
def print_s2n_output(response_dict, do_print_rec=False):
    print('*** Dictionary of S^n dictionaries ***')
    for name, attelt in response_dict.items():
        try:
            if name == 'records':
                print('{}: '.format(name))
                for respdict in attelt:
                    _print_oneprov_output(respdict, do_print_rec)
            else:
                print('{}: {}'.format(name, attelt))
        except:
            pass
    outelts = set(response_dict.keys())
    missing = S2nKey.response_keys().difference(outelts)
    extras = outelts.difference(S2nKey.response_keys())
    if missing:
        print('Missing elements: {}'.format(missing))
    if extras:
        print('Extra elements: {}'.format(extras))
    print('')


