import logging
import hashlib
import requests

from ckan import model
from ckan.lib.navl.validators import ignore_empty, not_empty

from ckanext.harvest.model import HarvestObject
from ckanext.harvest.model import HarvestObjectExtra as HOExtra
import ckanext.harvest.queue as queue

from ckanext.geodatagov.harvesters.base import GeoDataGovWAFHarvester, validate_profiles


class WAFCollectionHarvester(GeoDataGovWAFHarvester):

    def info(self):
        return {
            'name': 'waf-collection',
            'title': 'Web Accessible Folder (WAF) Collection',
            'description': 'A Web Accessible Folder (WAF) displaying a list of spatial metadata documents with a collection record'
            }

    def extra_schema(self):
        return {'validator_profiles': [unicode, ignore_empty, validate_profiles, lambda value: [value]],
                'collection_metadata_url': [not_empty, unicode]}

    def get_package_dict(self, iso_values, harvest_object):

        package_dict = super(WAFCollectionHarvester, self).get_package_dict(iso_values, harvest_object)

        collection_package_id = self._get_object_extra(harvest_object, 'collection_package_id')
        if collection_package_id:
            package_dict['extras']['collection_package_id'] = collection_package_id

        collection_metadata = self._get_object_extra(harvest_object, 'collection_metadata')
        if collection_metadata:
            package_dict['extras']['collection_metadata'] = collection_metadata

        return package_dict


    def gather_stage(self, harvest_job):
        log = logging.getLogger(__name__ + '.WAF.gather')
        log.debug('WafHarvester gather_stage for job: %r', harvest_job)


        self.harvest_job = harvest_job

        # Get source URL
        source_url = harvest_job.source.url

        self._set_source_config(harvest_job.source.config)

        collection_metadata_url = self.source_config.get('collection_metadata_url')

        if not collection_metadata_url:
            self._save_gather_error('collection url does not exist', harvest_job)
            return None

        try:
            response = requests.get(source_url, timeout=60)
            content = response.content
        except Exception, e:
            self._save_gather_error('Unable to get content for URL: %s: %r' % \
                                        (source_url, e),harvest_job)
            return None

        guid=hashlib.md5(collection_metadata_url.encode('utf8',errors='ignore')).hexdigest()

        existing_harvest_object = model.Session.\
            query(HarvestObject.guid, HarvestObject.package_id, HOExtra.value).\
            join(HOExtra, HarvestObject.extras).\
            filter(HOExtra.key=='collection_metadata').\
            filter(HOExtra.value=='true').\
            filter(HarvestObject.current==True).\
            filter(HarvestObject.harvest_source_id==harvest_job.source.id).first()

        if existing_harvest_object:
            status = 'changed'
            guid = existing_harvest_object.guid
            package_id = existing_harvest_object.package_id
        else:
            status, package_id = 'new', None

        obj = HarvestObject(job=harvest_job,
                            extras=[HOExtra(key='collection_metadata', value='true'),
                                    HOExtra(key='waf_location', value=collection_metadata_url),
                                    HOExtra(key='status', value=status)
                                   ],
                            guid=guid,
                            status=status,
                            package_id=package_id
                           )
        queue.fetch_and_import_stages(self, obj)
        if obj.state == 'ERROR':
            self._save_gather_error('Collection object failed to harvest, not harvesting', harvest_job)
            return None

        return GeoDataGovWAFHarvester.gather_stage(self, harvest_job, collection_package_id=obj.package_id)