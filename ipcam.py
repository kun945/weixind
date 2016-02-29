#!/usr/bin/env python
# encoding: utf-8

import requests
#from lxml import etree
from requests.auth import HTTPDigestAuth


__version__ = '0.1.0'
__author__ = 'Liang Cha (ckmx945@gmail.com)'


_IMAGE_METHODS = ('shot', 'photo', 'photoaf')

_AUDIO_TYPES = ('wav', 'aac', 'opus')

_HTTP_GET, _HTTP_POST = ('get', 'post')

_VIDEO_BOUNDARY = '--Ba4oTvQMY8ew04N8dcnM'

_XML_CONTENT_TYPE = 'application/xml'

_JSON_CONTENT_TYPE = 'application/json'

_IMAGE_CONTENT_TYPE = 'image/jpeg'

_VIDEO_CONTENT_TYPE = 'multipart/x-mixed-replace;boundary=Ba4oTvQMY8ew04N8dcnM'

_AUDIO_CONTENT_TYPES = ('audio/x-wav', )

class IPCamError(StandardError):

    def __init__(self, error_code, error_msg):
        self.error_code = error_code
        self.error_msg = error_msg
        StandardError.__init__(self, error_msg)

    def __str__(self):
        return '%d:%s' %(self.error_code, self.error_msg)


def _parse_params(**kw):
    '''Parse the parameters of the need'''
    params = []
    stream = False
    for k, v in kw.iteritems():
        #print _parse_params.func_name, k, v
        if k == 'stream':
            stream = v
            continue
        if v == None:
            params.append('%s=' %k)
        else:
            params.append('%s=%s' %(k, str(v)))
    return stream, '&'.join(params)


def _ipcam_http_call(ipcam, method, url, **kw):
    resp = None
    auth = None
    stream, params = _parse_params(**kw)
    if params:
        url = '%s?%s' %(url, params)
    #print _ipcam_http_call.func_name, url
    if ipcam._user and ipcam._pass:
        auth = HTTPDigestAuth(ipcam._user,ipcam._pass)
    if method == _HTTP_GET:
        resp = requests.get(url, auth=auth, stream=stream, timeout=8)
    if resp.status_code != 200:
        resp.close()
        raise IPCamError(4001, 'request server failed, status_code=%d' %resp.status_code)
    #print resp.headers['Content-Type']
    if resp.headers['Content-Type'] == _IMAGE_CONTENT_TYPE:
        return Image(resp)
    if resp.headers['Content-Type'] == _VIDEO_CONTENT_TYPE:
        return Video(resp)
    if resp.headers['Content-Type'] in _AUDIO_CONTENT_TYPES:
        return Audio(resp)
    if resp.headers['Content-Type'] == _XML_CONTENT_TYPE:
        return Xml(resp)
    if resp.headers['Content-Type'] == _JSON_CONTENT_TYPE:
        return Json(resp)
    raise IPCamError(4002, 'not support this content-type' %reasp.headers['Content-Type'])


def _video_header_parse(resp):
    '''Parse each frame header information'''
    headers = dict()
    for index in range(4):
        line = ''.join((resp.raw.readline()).strip().split())
        if not line:
            continue
        if index == 0:
            if line != _VIDEO_BOUNDARY:
                raise IPCamError(5001, 'video boundary not match')
            headers['boundary'] = line
            continue
        sline = line.split(':')
        headers[sline[0]] = sline[1]
    return headers


class IPcamResponse(object):

    def __init__(self, resp):
        self._resp = resp

    def read(self):
        pass

    def close(self):
        '''Disconnect'''
        self._resp.close()


class Xml(IPcamResponse):

    '''Dealing with XML response data'''

    def __init__(self, resp):
        IPcamResponse.__init__(self, resp)

    def read(self):
        return self._resp.content

    def __str__(self):
        return _XML_CONTENT_TYPE


class Json(Xml):

    '''Dealing with JSON response data'''

    def __init__(self, resp):
        Xml.__init__(self, resp)

    def __str__(self):
        return _JSON_CONTENT_TYPE


class Audio(IPcamResponse):

    '''Used to read the Audio data'''

    def __init__(self, resp):
        IPcamResponse.__init__(self, resp)

    def read(self, amt):
        '''Read audio data'''
        return self._resp.raw.read(amt)

    def __str__(self):
        return _AUDIO_CONTENT_TYPES


class Video(IPcamResponse):

    '''Used to read the video data'''

    def __init__(self, resp):
        IPcamResponse.__init__(self, resp)

    def read(self):
        '''Read one frame, return data'''
        headers = _video_header_parse(self._resp)
        content_length = int(headers['Content-Length'])
        return self._resp.raw.read(content_length)

    def __str__(self):
        return _VIDEO_CONTENT_TYPE


class Image(IPcamResponse):

    '''Used to read the image data'''

    def __init__(self, resp):
        IPcamResponse.__init__(self, resp)

    def read(self):
        '''Return all image date'''
        for chunk in self._resp.iter_content(self._resp.raw.tell()):
            return chunk

    def __str__(self):
        return _IMAGE_CONTENT_TYPE


class IPCamClient(object):

    '''IPCam client'''

    def __init__(self, ip, port, user=None, passw=None):
        '''
        Set ip, port and user information.

        :ip: IPCam ip
        :port: IPCam port
        :user: User name
        :pass: password
        '''

        self._ip = ip
        self._port = port
        self._user = user
        self._pass = passw
        self._resp = None

    def close(self):
        if not self._resp:
            self._resp.close()
            self._resp = None

    def __getattr__(self, attr):
        if attr in _IMAGE_METHODS:
            attr = '%s.jpg' %(attr)
        if attr == 'audio' or attr == 'video':
            stream = True
        return _Callable(self, attr)


class _Executable(object):

    def __init__(self, ipcam, method, path):
        self._ipcam = ipcam
        self._method = method
        self._path = path

    def __call__(self, **kw):
        url = 'http://%s:%d/%s' %(self._ipcam._ip, self._ipcam._port, self._path)
        return _ipcam_http_call(self._ipcam, self._method, url, **kw)

    def __str__(self):
        return '_Executable (%s)' %(self._path)

    __repr__ = __str__


class _Callable(object):

    def __init__(self, ipcam, name):
        self._ipcam = ipcam
        self._name = name

    def __getattr__(self, attr):
        #print self._name, attr
        if attr == 'get':
            return _Executable(self._ipcam, _HTTP_GET, self._name)
        if attr in _AUDIO_TYPES:
            name = '%s.%s' %(self._name, attr)
        else:
            name = '%s/%s' %(self._name, attr)
        return _Callable(self._ipcam, name)

    def __str__(self):
        return '_Callable (%s)' %(self._name)


if __name__ == '__main__':
    pass
