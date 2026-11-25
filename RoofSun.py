"""RoofSun : potentiel solaire des toitures, interface du plugin QGIS."""
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, QMetaType, Qt
from qgis.PyQt.QtGui import QIcon, QColor
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.core import QgsProject, QgsVectorLayer, QgsRasterLayer, QgsProcessingFeedback, QgsField, QgsFeature, NULL
from qgis.core import QgsCategorizedSymbolRenderer, QgsRendererCategory, QgsSymbol, QgsSingleSymbolRenderer
import requests
import json
import os
import tempfile
import processing

from .resources import *
from .RoofSun_dialog import RoofSunDialog
from .ModeleRoofSun import Roofsun


class RoofSun:
    def __init__(self, iface):
        self.iface = iface
        self.pluginDir = os.path.dirname(__file__)
        locale = QSettings().value('locale/userLocale')[0:2]
        localePath = os.path.join(
            self.pluginDir,
            'i18n',
            'RoofSun_{}.qm'.format(locale))

        if os.path.exists(localePath):
            self.translator = QTranslator()
            self.translator.load(localePath)
            QCoreApplication.installTranslator(self.translator)

        self.actions = []
        self.menu = self.tr(u'&RoofSun')
        self.firstStart = None
        self.dlg = None

    def tr(self, message):
        return QCoreApplication.translate('RoofSun', message)

    def addAction(self, iconPath, text, callback, enabledFlag=True, addToMenu=True, addToToolbar=True, statusTip=None, whatsThis=None, parent=None):
        icon = QIcon(iconPath)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabledFlag)

        if statusTip is not None:
            action.setStatusTip(statusTip)

        if whatsThis is not None:
            action.setWhatsThis(whatsThis)

        if addToToolbar:
            self.iface.addToolBarIcon(action)

        if addToMenu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)
        return action

    def initGui(self):
        iconPath = ':/plugins/roofsun/icon.png'
        self.addAction(
            iconPath,
            text=self.tr(u'RoofSun'),
            callback=self.run,
            parent=self.iface.mainWindow())

        self.firstStart = True

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&RoofSun'),
                action)
            self.iface.removeToolBarIcon(action)

    def run(self):
        if self.firstStart:
            self.firstStart = False
            self.dlg = RoofSunDialog()
        # liste rechargée à chaque ouverture pour voir les rasters ajoutés entre-temps
        self.remplirComboGti()

        result = self.dlg.exec()

        if not result:
            return

        codeInsee = self.dlg.getCodeCommuneSelect()
        coucheGti = self.dlg.getCoucheGtiSelect()

        if not codeInsee:
            self.iface.messageBar().pushWarning("RoofSun", "Veuillez sélectionner une commune.")
            return

        if not coucheGti:
            self.iface.messageBar().pushWarning("RoofSun", "Veuillez sélectionner un raster GTI.")
            return

        quartier = self.dlg.getQuartierSelect()
        self.traiterPotentielSolaire(codeInsee, coucheGti, quartier)

    def remplirComboGti(self):
        self.dlg.gtiComboBox.clear()
        self.dlg.gtiComboBox.addItem("Sélectionnez un raster GTI...", None)
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsRasterLayer):
                self.dlg.gtiComboBox.addItem(layer.name(), layer)

    def traiterPotentielSolaire(self, codeInsee, coucheGti, quartier):
        couches = self.chargerBatiZone(codeInsee, quartier)
        if not couches:
            return
        coucheBati, coucheZone = couches
        coucheResultat = self.executerModeleRoofsun(coucheBati, coucheZone, codeInsee, coucheGti, quartier)

        if coucheResultat:
            self.afficherMsgSucces(codeInsee, coucheResultat, quartier)
        else:
            self.iface.messageBar().pushCritical("RoofSun", "Erreur lors du traitement")

    def chargerBatiZone(self, codeInsee, quartier=None):
        if quartier:
            geomZone = self.getGeomQuartier(quartier, codeInsee)
            nomZone = quartier['nom']
        else:
            geomZone = self.getGeomCommune(codeInsee)
            nomZone = "commune"

        if not geomZone:
            self.iface.messageBar().pushWarning("RoofSun", f"Impossible d'obtenir la géométrie de la {nomZone}")
            return None

        bbox = self.calculerBboxGeom(geomZone)
        if not bbox:
            self.iface.messageBar().pushWarning("RoofSun", f"Impossible de calculer la BBOX pour {nomZone}")
            return None

        coucheBati = self.chargerBatiWfs(bbox, codeInsee, nomZone)
        if not coucheBati:
            self.iface.messageBar().pushWarning("RoofSun", "Aucun bâtiment chargé")
            return None

        # la BBOX déborde de la zone : le modèle ne garde que les bâtiments qui la touchent
        coucheZone = self.creerCoucheLimites(geomZone, f"Zone_{nomZone}")
        if not coucheZone.isValid():
            self.iface.messageBar().pushWarning("RoofSun", "Géométrie de la zone invalide")
            return None
        return coucheBati, coucheZone

    def getGeomCommune(self, codeInsee):
        url = f"https://geo.api.gouv.fr/communes/{codeInsee}?fields=nom,code,contour"
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return None

        data = r.json()
        return data.get('contour')

    def getGeomQuartier(self, quartier, codeInsee):
        typeQuartier = quartier.get('type')
        # pas de repli sur la commune : une zone introuvable doit se voir
        if typeQuartier == 'arrondissement':
            return self.getGeomArrondissement(quartier['code'])
        if typeQuartier == 'iris':
            return self.getGeomIrisWfs(quartier, codeInsee)
        return None

    def getGeomIrisWfs(self, iris, codeInsee):
        codeIris = iris.get('code')
        nomIris = iris.get('nom', '')

        if not codeIris:
            return None

        urlWfs = "https://data.geopf.fr/wfs/ows"
        typenames = [
            'STATISTICALUNITS.IRIS:contours_iris',
            'STATISTICALUNITS.IRISGE:iris_ge'
        ]

        for typename in typenames:
            filtreCql = f"code_iris='{codeIris}'"

            params = {
                'SERVICE': 'WFS',
                'VERSION': '2.0.0',
                'REQUEST': 'GetFeature',
                'TYPENAME': typename,
                'CQL_FILTER': filtreCql,
                'OUTPUTFORMAT': 'application/json',
                'SRSNAME': 'EPSG:4326'
            }

            response = requests.get(urlWfs, params=params, timeout=30)
            if response.status_code != 200:
                continue

            data = response.json()
            features = data.get('features', [])
            if not features:
                continue

            geometry = features[0].get('geometry')
            if geometry:
                return geometry

        return self.getGeomIrisNom(nomIris, codeInsee)

    def getGeomIrisNom(self, nomIris, codeInsee):
        nomRecherche = nomIris.replace('IRIS ', '').strip()
        urlWfs = "https://data.geopf.fr/wfs/ows"
        typenames = [
            'STATISTICALUNITS.IRIS:contours_iris',
            'STATISTICALUNITS.IRISGE:iris_ge'
        ]

        for typename in typenames:
            filtreCql = f"insee_com='{codeInsee}' AND nom_iris LIKE '%{nomRecherche}%'"

            params = {
                'SERVICE': 'WFS',
                'VERSION': '2.0.0',
                'REQUEST': 'GetFeature',
                'TYPENAME': typename,
                'CQL_FILTER': filtreCql,
                'OUTPUTFORMAT': 'application/json',
                'SRSNAME': 'EPSG:4326'
            }

            response = requests.get(urlWfs, params=params, timeout=30)
            if response.status_code != 200:
                continue

            data = response.json()
            features = data.get('features', [])
            if not features:
                continue

            geometry = features[0].get('geometry')
            if geometry:
                return geometry

        return None

    def getGeomArrondissement(self, codeArrondissement):
        url = f"https://geo.api.gouv.fr/communes/{codeArrondissement}?fields=contour"
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return None

        data = r.json()
        return data.get('contour')

    def calculerBboxGeom(self, geometry):
        geojson = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "properties": {},
                "geometry": geometry
            }]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.geojson', delete=False, encoding='utf-8') as f:
            json.dump(geojson, f)
            cheminTemp = f.name

        couche = QgsVectorLayer(cheminTemp, "temp_geometry", "ogr")
        if not couche.isValid():
            return None

        couche4326 = processing.run("native:reprojectlayer", {
            'INPUT': couche,
            'TARGET_CRS': 'EPSG:4326',
            'OUTPUT': 'memory:'
        })['OUTPUT']

        bbox = couche4326.extent()
        xmin, ymin, xmax, ymax = bbox.xMinimum(), bbox.yMinimum(), bbox.xMaximum(), bbox.yMaximum()

        return f"{xmin},{ymin},{xmax},{ymax}"

    def chargerBatiWfs(self, bbox, codeInsee, nomZone):
        urlWfs = "https://data.geopf.fr/wfs/ows"
        taillePage = 5000
        features = []
        # le WFS plafonne le nombre d'objets par requête : on pagine jusqu'à la dernière page
        while True:
            params = {
                'SERVICE': 'WFS',
                'VERSION': '2.0.0',
                'REQUEST': 'GetFeature',
                'TYPENAME': 'BDTOPO_V3:batiment',
                'BBOX': f"{bbox},EPSG:4326",
                'OUTPUTFORMAT': 'application/json',
                'SRSNAME': 'EPSG:4326',
                'SORTBY': 'cleabs',
                'COUNT': taillePage,
                'STARTINDEX': len(features)
            }
            response = requests.get(urlWfs, params=params, timeout=120)
            if response.status_code != 200:
                self.iface.messageBar().pushWarning("RoofSun", f"Erreur WFS : HTTP {response.status_code}")
                return None
            page = response.json().get('features', [])
            features.extend(page)
            if len(page) < taillePage:
                break

        if not features:
            self.iface.messageBar().pushWarning("RoofSun", f"Aucun bâtiment trouvé dans la {nomZone}")
            return None

        geojsonBati = {"type": "FeatureCollection", "features": features}
        with tempfile.NamedTemporaryFile(mode='w', suffix='.geojson', delete=False, encoding='utf-8') as f:
            json.dump(geojsonBati, f)
            cheminBati = f.name

        coucheBati = QgsVectorLayer(cheminBati, f"Bâtiments_{codeInsee}", "ogr")
        if not coucheBati.isValid():
            self.iface.messageBar().pushWarning("RoofSun", "Couche bâtiments invalide")
            return None

        bati2154 = processing.run("native:reprojectlayer", {
            'INPUT': coucheBati,
            'TARGET_CRS': 'EPSG:2154',
            'OUTPUT': 'memory:'
        })['OUTPUT']

        coucheCorrigee = self.creerCoucheCorrigee(bati2154)
        return coucheCorrigee

    def creerCoucheCorrigee(self, coucheOrigine):
        crs = coucheOrigine.crs()
        coucheCorrigee = QgsVectorLayer(f"MultiPolygon?crs={crs.authid()}", "Bâtiments_corrigés", "memory")
        provider = coucheCorrigee.dataProvider()

        champs = [
            QgsField("NATURE", QMetaType.Type.QString, len=50),
            QgsField("Z_MAX_TOIT", QMetaType.Type.Double),
            QgsField("Z_MIN_TOIT", QMetaType.Type.Double)
        ]
        provider.addAttributes(champs)
        coucheCorrigee.updateFields()

        mappingChamps = {
            'NATURE': ['nature', 'NATURE'],
            'Z_MAX_TOIT': ['altitude_maximale_toit', 'Z_MAX_TOIT'],
            'Z_MIN_TOIT': ['altitude_minimale_toit', 'Z_MIN_TOIT']
        }

        coucheCorrigee.startEditing()

        for featureOrigine in coucheOrigine.getFeatures():
            newFeature = QgsFeature(coucheCorrigee.fields())
            newFeature.setGeometry(featureOrigine.geometry())

            for champCible, champsSource in mappingChamps.items():
                valeur = None
                for champSource in champsSource:
                    if champSource in featureOrigine.fields().names():
                        valeurOrigine = featureOrigine[champSource]
                        if valeurOrigine is not NULL and valeurOrigine is not None:
                            valeur = valeurOrigine
                            break

                if valeur is None:
                    if champCible == "NATURE":
                        valeur = "Indifférenciée"
                    else:
                        valeur = 0.0

                newFeature[champCible] = valeur

            provider.addFeature(newFeature)

        coucheCorrigee.commitChanges()
        return coucheCorrigee

    def executerModeleRoofsun(self, coucheBati, coucheZone, codeInsee, coucheGti, quartier=None):
        fichierTemp = tempfile.NamedTemporaryFile(suffix='.gpkg', delete=False)
        cheminTemp = fichierTemp.name
        fichierTemp.close()

        algorithme = Roofsun()
        parametres = {
            'btiment': coucheBati,
            'zone': coucheZone,
            'global_tilted_irradiance_gti': coucheGti,
            'IndiceToiture': cheminTemp
        }

        feedback = QgsProcessingFeedback()
        processing.run(algorithme, parametres, feedback=feedback)

        coucheResultat = QgsVectorLayer(cheminTemp, f"Potentiel_Solaire_{codeInsee}", "ogr")
        if not coucheResultat.isValid():
            return None

        QgsProject.instance().addMapLayer(coucheResultat)
        self.appliquerSymbologie(coucheResultat)
        self.ajouterFondOsm()
        self.ajouterLimitesTerritoriales(codeInsee, quartier)
        self.reorganiserCouches(coucheResultat, codeInsee, quartier)

        return coucheResultat

    def appliquerSymbologie(self, couche):
        nomsChamps = [field.name() for field in couche.fields()]
        if 'indice' not in nomsChamps:
            return

        categories = []
        reglesSymbologie = [
            ('Très élevé', "#860624", "Potentiel très élevé"),
            ('Élevé', '#d73027', "Potentiel élevé"),
            ('Moyen', '#fdae61', "Potentiel moyen"),
            ('Faible', '#abd9e9', "Potentiel faible"),
            ('Très faible', '#4575b4', "Potentiel très faible")
        ]

        for valeur, couleur, libelle in reglesSymbologie:
            symbol = QgsSymbol.defaultSymbol(couche.geometryType())
            symbol.setColor(QColor(couleur))
            symbol.setOpacity(0.9)
            symbol.symbolLayer(0).setStrokeColor(QColor('#00000000'))
            symbol.symbolLayer(0).setStrokeWidth(0.0)

            category = QgsRendererCategory(valeur, symbol, libelle)
            categories.append(category)

        renderer = QgsCategorizedSymbolRenderer('indice', categories)
        couche.setRenderer(renderer)
        couche.triggerRepaint()

    def ajouterLimitesTerritoriales(self, codeInsee, quartier=None):
        geomCommune = self.getGeomCommune(codeInsee)
        if geomCommune:
            coucheCommune = self.creerCoucheLimites(geomCommune, f"Limite_Commune_{codeInsee}")
            QgsProject.instance().addMapLayer(coucheCommune)

        if quartier:
            geomQuartier = self.getGeomQuartier(quartier, codeInsee)
            if geomQuartier:
                coucheQuartier = self.creerCoucheLimites(geomQuartier, f"Limite_{quartier['nom']}")
                QgsProject.instance().addMapLayer(coucheQuartier)

    def creerCoucheLimites(self, geometry, nomCouche):
        geojson = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "properties": {"name": nomCouche},
                "geometry": geometry
            }]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.geojson', delete=False, encoding='utf-8') as f:
            json.dump(geojson, f)
            cheminTemp = f.name

        couche = QgsVectorLayer(cheminTemp, nomCouche, "ogr")

        if couche.isValid():
            symbol = QgsSymbol.defaultSymbol(couche.geometryType())
            symbol.setColor(QColor('#FFFFFF'))
            symbol.setOpacity(0.3)
            symbol.symbolLayer(0).setStrokeColor(QColor('#000000'))
            symbol.symbolLayer(0).setStrokeWidth(0.8)
            symbol.symbolLayer(0).setStrokeStyle(Qt.PenStyle.SolidLine)

            renderer = QgsSingleSymbolRenderer(symbol)
            couche.setRenderer(renderer)

        return couche

    def ajouterFondOsm(self):
        couchesExistantes = QgsProject.instance().mapLayersByName("OpenStreetMap")
        if couchesExistantes:
            for coucheOsm in couchesExistantes:
                renderer = coucheOsm.renderer()
                if renderer:
                    renderer.setOpacity(0.7)
                coucheOsm.triggerRepaint()
            return

        urlOsm = "type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        coucheOsm = QgsRasterLayer(urlOsm, "OpenStreetMap", "wms")

        if coucheOsm.isValid():
            renderer = coucheOsm.renderer()
            if renderer:
                renderer.setOpacity(0.7)
            QgsProject.instance().addMapLayer(coucheOsm)

    def reorganiserCouches(self, coucheResultat, codeInsee, quartier=None):
        root = QgsProject.instance().layerTreeRoot()
        couchesCibles = [
            "OpenStreetMap",
            f"Limite_Commune_{codeInsee}",
        ]

        if quartier:
            couchesCibles.append(f"Limite_{quartier['nom']}")

        couchesCibles.append(coucheResultat.name())

        for i, nomCouche in enumerate(reversed(couchesCibles)):
            couche = QgsProject.instance().mapLayersByName(nomCouche)
            if couche:
                nodeCouche = root.findLayer(couche[0].id())
                if nodeCouche:
                    clone = nodeCouche.clone()
                    root.insertChildNode(i, clone)
                    parent = nodeCouche.parent()
                    parent.removeChildNode(nodeCouche)

    def afficherMsgSucces(self, codeInsee, coucheResultat, quartier):
        infoQuartier = ""
        if quartier:
            nomQuartier = quartier.get('nom', 'Quartier')
            infoQuartier = f" - {nomQuartier}"

        QMessageBox.information(
            self.iface.mainWindow(),
            "RoofSun – Succès",
            f"Commune {codeInsee}{infoQuartier} traitée !\n{coucheResultat.featureCount()} toitures analysées.\n\nLes limites territoriales ont été ajoutées au projet."
        )