# -*- coding: utf-8 -*-
import json, traceback, time
from qgis.core import *
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.QtNetwork import *

from DlgWaiting import DlgWaiting
from GeosismaWindow import GeosismaWindow as gw

class DownloadSopralluoghi(DlgWaiting):
    
    # signals
    done = pyqtSignal(bool)
    singleDone = pyqtSignal(bool)
    message = pyqtSignal(str, int)

    def __init__(self, parent=None, bbox=None, srid=None):
        DlgWaiting.__init__(self, parent)
        self.singleFinished = True
        self.allFinished = True
        
        self.jsonSopralluoghi = None
        self.bbox = bbox # as QgsRectangle
        self.srid = srid
        self.total_count = None
        
        self.manager = QgsNetworkAccessManager.instance()
        # clean listeners to avoid overlap 
        try:
            self.manager.finished.disconnect()
        except:
            pass
        # add new listeners
        self.manager.finished.connect(self.replyFinished)

        #self.setWindowModality(Qt.ApplicationModal)
    
    def __del__(self):
        try:
            self.manager.finished.disconnect(self.replyFinished)
        except Exception:
            pass
    
    def run(self):
        try:
            # init progress bar
            self.reset()
            self.setWindowTitle( self.tr("Scarica  i record del layer '%s'" % gw.instance().LAYER_GEOM_SOPRALLUOGHI ))
            #self.setRange( 0, 1 )
            QApplication.setOverrideCursor(Qt.WaitCursor)

            # set semaphores
            self.done.connect(self.setAllFinished)
            self.singleDone.connect(self.setSingleFinished)

            # for each request api
            self.allFinished = False

            # create db
            self.jsonRequest = None
            self.singleFinished = False
            self.DownloadSopralluoghi()
            
            # whait end of single request
            while (not self.singleFinished):
                qApp.processEvents()
                time.sleep(0.1)
            
            # archive request in self.downloadedTeams
            #self.downloadedTeams[index]["downloadedRequests"][requestApi] = self.jsonSopralluoghi
            #self.downloadedRequests.append(self.jsonSopralluoghi)
            
            self.onProgress()
            
            # some other emitted done signal
            if (self.allFinished):
                return
            
            self.done.emit(True)
            
        except Exception as e:
            QApplication.restoreOverrideCursor()
            try:
                traceback.print_exc()
            except:
                pass
            self.done.emit(False)
            self.message.emit(e.message, QgsMessageLog.CRITICAL)
            raise e
        finally:
            QApplication.restoreOverrideCursor()

    def setSingleFinished(self, success):
        self.singleFinished = True

    def setAllFinished(self, success):
        self.allFinished = True

    def DownloadSopralluoghi(self):
        
        # get connection conf
        settings = QSettings()
        sopralluoghiUrl = settings.value("/rt_geosisma_offline/sopralluoghiUrl", "/api/v1/sopralluoghi/")
        self.baseApiUrl = settings.value("/rt_geosisma_offline/baseApiUrl", "http://geosisma-test.faunalia.it/")

        # create json parametr for the bbox... without using geojson pytion module to avoid dependency
        geojsonbbox = """{"type": "Polygon", "coordinates": [[[%(minx)s, %(miny)s], [%(minx)s, %(maxy)s], [%(maxy)s, %(maxy)s], [%(maxx)s, %(miny)s], [%(minx)s, %(miny)s]]], "crs": {"type": "name", "properties": {"name": "EPSG:%(srid)s"}}}"""
        geojsonbbox = geojsonbbox % { "minx":self.bbox.xMinimum(), "miny":self.bbox.yMinimum(), "maxx":self.bbox.xMaximum(), "maxy":self.bbox.yMaximum(), "srid":self.srid }

        # for each request api
        request = QNetworkRequest()
        url = QUrl(self.baseApiUrl + sopralluoghiUrl)
        url.addQueryItem("the_geom__contained", geojsonbbox )
        url.addQueryItem("format", "json")
        request.setUrl(url)
        
        message = self.tr("Download %s with query: %s and bbox: %s" % (gw.instance().LAYER_GEOM_SOPRALLUOGHI, url.toString(), geojsonbbox ) )
        self.message.emit(message, QgsMessageLog.INFO)

        # start download
        self.manager.get(request)
        
        # wait request finish to go to the next
        self.singleFinished = False

    def replyFinished(self, reply):
        if self is None:
            return
        
        # need auth
        if reply.error() == QNetworkReply.AuthenticationRequiredError:
            gw.instance().autenthicated = False
            message = self.tr(u"Autenticazione fallita")
            self.message.emit(message, QgsMessageLog.WARNING)
            self.done.emit(False)
            return
        
        # received error
        if reply.error():
            message = self.tr("Errore nella HTTP Request: %d - %s" % (reply.error(), reply.errorString()) )
            self.message.emit(message, QgsMessageLog.WARNING)
            self.done.emit(False)
            return
        
        # well authenticated :)
        gw.instance().autenthicated = True
        gw.instance().authenticationRetryCounter = 0
        
        # gets elements
        from json import loads
        raw = reply.readAll()
        try:
            json = loads(raw.data())
        except Exception:
            try:
                traceback.print_exc()
            except:
                pass
            self.done.emit(False)
            return

        # count how many to download
        if "meta" in json:
            if "total_count" in json["meta"]:
                if not self.total_count:
                    self.total_count = json["meta"]["total_count"]
                    self.setRange( 0, self.total_count )
        
        # check if return more than 20 elements (e.g. for the super user)
        if "objects" in json:
            jsonSopralluoghi = json["objects"] # get array of dicts
        else:
            jsonSopralluoghi = [json]
        for record in jsonSopralluoghi:
            gw.instance().sopralluoghi.append(record)
            self.onProgress()
        
        # manage get of other elements if available 
        if "meta" in json:
            if "next" in json["meta"]:
                nextUrl = json["meta"]["next"]
                if nextUrl:
                    self.message.emit(nextUrl, QgsMessageLog.INFO)
                    
                    request = QNetworkRequest()
                    url = QUrl.fromEncoded(self.baseApiUrl + nextUrl)
                    request.setUrl(url)
                     
                    self.manager.get(request)
                    return

        #gw.instance().downloadedRequests.append(jsonSopralluoghi)
        
        # successfully end
        self.singleDone.emit(True)
