# -*- coding: utf-8 -*-
"""
Zegami Ltd.
Apache 2.0
"""

from io import BytesIO
import pandas as pd
from PIL import Image
from time import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .source import Source


class Collection():
    
    @staticmethod
    def _construct_collection(client, workspace, collection_dict):
        assert type(collection_dict) == dict,\
            'Expected collection_dict to be a dict, not {}'.format(collection_dict)
        v = collection_dict['version'] if 'version' in collection_dict.keys() else 1
        if v == 1:
            return Collection(client, workspace, collection_dict)
        elif v == 2:
            return CollectionV2(client, workspace, collection_dict)
    
    
    def __init__(self, client, workspace, collection_dict):
        self._client = client
        self._data = collection_dict
        self._workspace = workspace
        self._check_data()
        self._check_version()
        
        
    @property
    def client(): pass
    @client.getter
    def client(self):
        assert self._client, 'Client is not valid'
        return self._client
    
    
    @property
    def name(): pass
    @name.getter
    def name(self) -> str:
        self._check_data()
        assert 'name' in self._data.keys(),\
            'Collection\'s data didn\'t have a \'name\' key'
        return self._data['name']
    
        
    @property
    def id(): pass
    @id.getter
    def id(self):
        self._check_data()
        assert 'id' in self._data.keys(),\
            'Collection\'s data didn\'t have an \'id\' key'
        return self._data['id']
    
    
    @property
    def _dataset_id(): pass
    @_dataset_id.getter
    def _dataset_id(self) -> str:
        self._check_data()
        assert 'dataset_id' in self._data.keys(),\
            'Collection\'s data didn\'t have a \'dataset_id\' key'
        return self._data['dataset_id']
        
        
    @property
    def version(): pass
    @version.getter
    def version(self):
        self._check_data()
        return self._data['version'] if 'version' in self._data.keys() else 1
    
    
    @property
    def workspace(): pass
    @workspace.getter
    def workspace(self):
        return self._workspace
    
    
    @property
    def workspace_id(): pass
    @workspace_id.getter
    def workspace_id(self):
        assert self.workspace is not None,\
            'Tried to get a workspace ID when no workspace was set'
        return self.workspace.id
    
    
    @property
    def url(): pass
    @url.getter
    def url(self):
        return '{}/collections/{}-{}'.format(
            self.client.HOME, self.workspace_id, self.id)
    
    
    @property
    def sources(): pass
    @sources.getter
    def sources(self):
        if self.version < 2:
            print('{} is an old-style collection and does not support multiple image sources'.format(self.name))
            return []
        
        
    def show_sources(self):
        print('{} is an old-style collection and does not support multiple image sources'.format(self.name))
        
        
    @property
    def rows(): pass
    @rows.getter
    def rows(self):
        ''' Returns all data rows of the collection as a Pandas DataFrame. '''
        
        c = self.client
        
        # Obtain the metadata bytes from Zegami
        url = '{}/{}/project/{}/datasets/{}/file'.format(
            c.HOME, c.API_0, self.workspace_id, self._dataset_id)
        r = c._auth_get(url, return_response=True)
        tsv_bytes = BytesIO(r.content)
        
        # Convert into a pd.DataFrame
        try:
            df = pd.read_csv(tsv_bytes, sep='\t')
        except:
            try:
                df = pd.read_excel(tsv_bytes)
            except:
                print('Warning - failed to open metadata as a dataframe, returned '
                      'the tsv bytes instead.')
                return tsv_bytes
    
        return df
    
    
    def get_rows_by_filter(self, collection, filters):
        ''' Gets rows of metadata in a collection by a flexible filter.
        
        The filter should be a dictionary describing what to permit through
        any specified columns.
        
        Example:
            row_filter = { 'breed': ['Cairn', 'Dingo'] }
            
        This would only return rows whose 'breed' column matches 'Cairn'
        or 'Dingo'. '''
        
        assert type(filters) == dict, 'Filters should be a dict.'
        rows = self.rows
        
        for fk, fv in filters.items():
            if not type(fv) == list:
                fv = [fv]
            rows = rows[rows[fk].isin(fv)]
        return rows
    
    
    def get_image_urls(self, rows, source=0):
        ''' Converts rows into their corresponding image URLs. You can use
        these URLs with download_image()/download_image_batch(). '''
        
        # Turn the provided 'rows' into a list of ints
        if type(rows) == pd.DataFrame:
            indices = list(rows.index)
            
        elif type(rows) == list:
            indices = [int(r) for r in rows]
            
        elif type(rows) == int:
            indices = [rows]
            
        else:
            raise ValueError('Invalid rows argument, \'{}\' not supported'\
                             .format(type(rows)))
                
        # Convert the row-space indices into imageset-space indices
        lookup = self._get_image_meta_lookup(source)
        imageset_indices = [lookup[i] for i in indices]
        
        # Convert these into URLs
        c = self.client
        return ['{}/{}/project/{}/imagesets/{}/images/{}/data'.format(
            c.HOME, c.API_0, self.workspace_id, self._get_imageset_id(source),
            i) for i in imageset_indices]
    
    
    def download_image(self, url):
        ''' Downloads an image into memory as a PIL.Image. For input, see
        Collection.get_image_urls(). '''
        r = self.client._auth_get(url, return_response=True, stream=True)
        r.raw.decode = True
        return Image.open(r.raw)
        
        
    def download_image_batch(self, urls, max_workers=50, show_time_taken=True):
        ''' Downloads multiple images into memory (each as a PIL.Image)
        concurrently.
        
        Please be aware that these images are being downloaded into memory,
        if you download a huge collection of images you may eat up your
        RAM! '''
        
        def download_single(index, url):
            return (index, self.download_image(url))
        
        t = time()
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            
            futures = [ex.submit(download_single, i, u) for i, u in enumerate(urls)]
        
            images = {}
            for f in as_completed(futures):
                i, img = f.result()
                images[i] = img
        
        if show_time_taken:
            print('\nDownloaded {} images in {:.2f} seconds.'.format(
                len(images), time() - t))
        
        # Results are a randomly ordered dictionary of results, so reorder them
        ordered = []
        for i in range(len(images)):
            ordered.append(images[i])
                
        return ordered
        
        
    def _check_data(self) -> None:
        assert self._data, 'Collection had no self._data set'
        assert type(self._data) == dict,\
            'Collection didn\'t have a dict for its data ({})'.format(type(self._data))
            
            
    def _check_version(self) -> None:
        v = self.version
        class_v = 2 if isinstance(self, CollectionV2) else 1
        
        assert v == class_v, 'Collection data indicates the class used to '\
        'construct this collection is the wrong version. v{} class vs v{} data'\
        .format(class_v, v)
    
    
    def _get_imageset_id(self, source=0) -> str:
        self._check_data()
        assert 'imageset_id' in self._data,\
            'Collection\'s data didn\'t have an \'imageset_id\' key'
        return self._data['imageset_id']
    
    
    def _join_id_to_lookup(self, join_id):
        assert type(join_id) == str, 'Expected join_id to be string: {}'.format(join_id)
        c = self.client
        url = '{}/{}/project/{}/datasets/{}'.format(c.HOME, c.API_0, self.workspace_id, join_id)
        return c._auth_get(url)['dataset']['imageset_indices']
    
    
    def _get_image_meta_lookup(self, source=0) -> list:
        self._check_data()
        assert 'imageset_dataset_join_id' in self._data.keys(),\
            'Collection\'s data didn\'t have an \'imageset_dataset_join_id\' key'
        join_id = self._data['imageset_dataset_join_id']
        return self._join_id_to_lookup(join_id)
        
    
    def __len__(self) -> int:
        self._check_data()
        assert 'total_data_items' in self._data.keys(),\
            'Collection\'s data didn\'t have a \'total_data_items\' key'
        return self._data['total_data_items']
        
        

class CollectionV2(Collection):
    
    def __init__(self, client, workspace, collection_dict):
        super(CollectionV2, self).__init__(client, workspace, collection_dict)
    
    
    @property
    def sources(): pass
    @sources.getter
    def sources(self) -> list:
        assert 'image_sources' in self._data.keys(),\
            'Expected to find \'image_sources\' in collection but didn\'t: {}'\
            .format(self._data)
        return [Source(self, s) for s in self._data['image_sources']]
    
    
    def show_sources(self):
        ss = self.sources
        print('\nImage sources ({}):'.format(len(ss)))
        for s in ss:
            print('{} : {}'.format(s._imageset_id, s.name))
        
        
    def _get_imageset_id(self, source=0) -> str:
        ''' Source can be an int or a Source instance from this collection. '''
        self._check_data()
        self._check_version()
        return self._parse_source(source)._imageset_id
    
    
    def _get_image_meta_lookup(self, source=0) -> list:
        self._check_data()
        join_id = self._parse_source(source)._imageset_dataset_join_id
        return self._join_id_to_lookup(join_id)
        
        
    def _parse_source(self, source):
        ss = self.sources
        
        # If an index is given, check the index is sensible and return a Source
        if type(source) == int:
            assert source >= 0,\
                'Expected source to be a positive int'
            assert source < len(ss),\
                'Source not valid for number of available sources (index {} for list length {})'\
                .format(source, len(ss))
            return ss[source]
        
        # If a Source is given, check it belongs to this collection and return
        assert isinstance(source, Source), 'Provided source was neither an '\
        'int nor a Source instance: {}'.format(source)
        
        for s in ss:
            if s.id == source.id:
                return source
            
        raise Exception('Provided source was a Source instance, but didn\'t '\
                        'belong to this collection ({})'.format(self.name))
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        