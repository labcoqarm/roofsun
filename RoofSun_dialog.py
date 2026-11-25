"""RoofSun : fenêtre de choix de la zone (région, département, EPCI, commune, IRIS)."""

import os
import requests
from typing import List, Dict

from qgis.PyQt import uic
from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import Qt
from qgis.core import QgsMessageLog, Qgis

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'RoofSun_dialog_base.ui'))

class RoofSunDialog(QtWidgets.QDialog, FORM_CLASS):
    API_TIMEOUT = 10
    WFS_TIMEOUT = 30
    WFS_TIMEOUT_LONG = 60
    WFS_URL = 'https://data.geopf.fr/wfs/ows'
    WFS_TYPENAME = 'STATISTICALUNITS.IRIS:contours_iris'
    BATCH_SIZE_BBOX = 1000
    BATCH_SIZE_FULL = 5000
    MAX_IRIS_PER_COMMUNE = 5000

    OVERSEAS_REGIONS = ['01', '02', '03', '04', '06', 'COM']
    EXCLUDED_DEPARTEMENTS = ['75']
    EXCLUDED_COMMUNES = ['75056']

    ARRONDISSEMENTS = {
        '13055': [
            {'type': 'arrondissement', 'nom': '1er arrondissement', 'code': '13201', 'numero': 1},
            {'type': 'arrondissement', 'nom': '2e arrondissement', 'code': '13202', 'numero': 2},
            {'type': 'arrondissement', 'nom': '3e arrondissement', 'code': '13203', 'numero': 3},
            {'type': 'arrondissement', 'nom': '4e arrondissement', 'code': '13204', 'numero': 4},
            {'type': 'arrondissement', 'nom': '5e arrondissement', 'code': '13205', 'numero': 5},
            {'type': 'arrondissement', 'nom': '6e arrondissement', 'code': '13206', 'numero': 6},
            {'type': 'arrondissement', 'nom': '7e arrondissement', 'code': '13207', 'numero': 7},
            {'type': 'arrondissement', 'nom': '8e arrondissement', 'code': '13208', 'numero': 8},
            {'type': 'arrondissement', 'nom': '9e arrondissement', 'code': '13209', 'numero': 9},
            {'type': 'arrondissement', 'nom': '10e arrondissement', 'code': '13210', 'numero': 10},
            {'type': 'arrondissement', 'nom': '11e arrondissement', 'code': '13211', 'numero': 11},
            {'type': 'arrondissement', 'nom': '12e arrondissement', 'code': '13212', 'numero': 12},
            {'type': 'arrondissement', 'nom': '13e arrondissement', 'code': '13213', 'numero': 13},
            {'type': 'arrondissement', 'nom': '14e arrondissement', 'code': '13214', 'numero': 14},
            {'type': 'arrondissement', 'nom': '15e arrondissement', 'code': '13215', 'numero': 15},
            {'type': 'arrondissement', 'nom': '16e arrondissement', 'code': '13216', 'numero': 16}
        ],
        '69123': [
            {'type': 'arrondissement', 'nom': '1er arrondissement', 'code': '69381', 'numero': 1},
            {'type': 'arrondissement', 'nom': '2e arrondissement', 'code': '69382', 'numero': 2},
            {'type': 'arrondissement', 'nom': '3e arrondissement', 'code': '69383', 'numero': 3},
            {'type': 'arrondissement', 'nom': '4e arrondissement', 'code': '69384', 'numero': 4},
            {'type': 'arrondissement', 'nom': '5e arrondissement', 'code': '69385', 'numero': 5},
            {'type': 'arrondissement', 'nom': '6e arrondissement', 'code': '69386', 'numero': 6},
            {'type': 'arrondissement', 'nom': '7e arrondissement', 'code': '69387', 'numero': 7},
            {'type': 'arrondissement', 'nom': '8e arrondissement', 'code': '69388', 'numero': 8},
            {'type': 'arrondissement', 'nom': '9e arrondissement', 'code': '69389', 'numero': 9}
        ]
    }

    def __init__(self, parent=None):
        super(RoofSunDialog, self).__init__(parent)
        self.setupUi(self)
        self.selectedGtiLayer = None
        self.selectedIrisInArrondissement = None
        self.initUI()
        self.chargerRegions()

    def initUI(self):
        for combo in [self.departementCombo, self.epciCombo, self.communeCombo, self.quartierCombo]:
            combo.setEnabled(False)
        self.regionCombo.currentIndexChanged.connect(self.changementRegion)
        self.departementCombo.currentIndexChanged.connect(self.changementDepartement)
        self.epciCombo.currentIndexChanged.connect(self.changementEpci)
        self.communeCombo.currentIndexChanged.connect(self.changementCommune)
        self.quartierCombo.currentIndexChanged.connect(self.changementQuartier)
        self.gtiComboBox.currentIndexChanged.connect(self.changementGti)

    def apiGet(self, url: str, timeout: int = API_TIMEOUT):
        response = requests.get(url, timeout=timeout)
        if response.status_code == 200:
            return response.json()
        QgsMessageLog.logMessage(f"Erreur API {url}: HTTP {response.status_code}", "RoofSun", Qgis.Warning)
        return None

    def chargerRegions(self):
        self.regionCombo.clear()
        self.regionCombo.addItem("Sélectionnez une région...", None)
        data = self.apiGet("https://geo.api.gouv.fr/regions?fields=nom,code")
        if not data:
            self.regionCombo.addItem("Erreur de chargement", None)
            return

        for region in data:
            if region['code'] not in self.OVERSEAS_REGIONS:
                self.regionCombo.addItem(region['nom'], region['code'])

    def changementRegion(self, index):
        codeReg = self.regionCombo.itemData(index)
        self.resetCombosFrom(1)

        if not codeReg:
            return

        self.departementCombo.setEnabled(True)
        data = self.apiGet(f"https://geo.api.gouv.fr/departements?codeRegion={codeReg}&fields=nom,code")
        if not data:
            return

        self.departementCombo.addItem("Sélectionnez un département...", None)
        for dep in data:
            if dep['code'].startswith(('97', '98')):
                continue
            if dep['code'] in self.EXCLUDED_DEPARTEMENTS:
                continue
            self.departementCombo.addItem(dep['nom'], dep['code'])

    def changementDepartement(self, index):
        codeDep = self.departementCombo.itemData(index)
        self.resetCombosFrom(2)

        if not codeDep:
            return

        self.epciCombo.setEnabled(True)
        self.communeCombo.setEnabled(True)

        data = self.apiGet(f"https://geo.api.gouv.fr/epcis?codeDepartement={codeDep}&fields=nom,code")
        if data:
            self.epciCombo.addItem("Sélectionnez un EPCI...", None)
            for epci in data:
                self.epciCombo.addItem(epci['nom'], epci['code'])

        self.chargerCommunesParDepartement(codeDep)

    def changementEpci(self, index):
        codeEpci = self.epciCombo.itemData(index)
        codeDep = self.departementCombo.itemData(self.departementCombo.currentIndex())

        if codeEpci:
            self.chargerCommunesParEpci(codeEpci)
        if codeDep and index == 0:
            self.chargerCommunesParDepartement(codeDep)

    def changementCommune(self):
        codeInsee = self.getCodeCommuneSelect()
        nomCommune = self.communeCombo.currentText()
        self.quartierCombo.clear()

        if not codeInsee or nomCommune == "Sélectionnez une commune...":
            self.quartierCombo.setEnabled(False)
            return

        self.quartierCombo.setEnabled(True)
        QgsMessageLog.logMessage(f"Chargement pour {nomCommune} ({codeInsee})...", "RoofSun", Qgis.Info)

        if codeInsee in self.ARRONDISSEMENTS:
            self.quartierCombo.addItem("Sélectionnez un arrondissement...", None)
            self.chargerArrondissementsManuel(codeInsee, nomCommune)
        else:
            self.chargerIris(codeInsee, nomCommune)

    def chargerArrondissementsManuel(self, codeInsee: str, nomCommune: str):
        QgsMessageLog.logMessage(f"Chargement des arrondissements pour {nomCommune}", "RoofSun", Qgis.Info)
        arrondissements = self.ARRONDISSEMENTS.get(codeInsee, [])

        for arrond in arrondissements:
            self.quartierCombo.addItem(arrond['nom'], arrond)
        QgsMessageLog.logMessage(f"{len(arrondissements)} arrondissements chargés", "RoofSun", Qgis.Info)

    def changementQuartier(self):
        quartier = self.getQuartierSelect()
        self.selectedIrisInArrondissement = None

        if not quartier:
            return

        if quartier.get('type') != 'arrondissement':
            return

        codeArrond = quartier.get('code')
        nomArrond = quartier.get('nom')

        QgsMessageLog.logMessage(f"Chargement des IRIS pour {nomArrond}...", "RoofSun", Qgis.Info)
        listeIris = self.getAllIris(codeArrond)

        if not listeIris:
            QgsMessageLog.logMessage(f"Aucun IRIS trouvé pour cet arrondissement", "RoofSun", Qgis.Warning)
            self.quartierCombo.setCurrentIndex(0)
            return

        for iris in listeIris:
            iris['parent_arrondissement'] = codeArrond

        dialogIris = DialogSelectionIris(listeIris, nomArrond, self)
        if not dialogIris.exec():
            self.quartierCombo.setCurrentIndex(0)
            QgsMessageLog.logMessage(f"Dialogue annulé, retour à la sélection", "RoofSun", Qgis.Warning)
            return

        irisSelect = dialogIris.getIrisSelect()
        if not irisSelect:
            self.quartierCombo.setCurrentIndex(0)
            QgsMessageLog.logMessage(f"Aucun IRIS sélectionné, retour à la sélection", "RoofSun", Qgis.Warning)
            return

        self.selectedIrisInArrondissement = irisSelect
        QgsMessageLog.logMessage(f"IRIS sélectionné : {irisSelect['nom']}", "RoofSun", Qgis.Info)

    def chargerIris(self, codeInsee: str, nomCommune: str):
        listeIris = self.getAllIris(codeInsee)
        if not listeIris:
            QgsMessageLog.logMessage(f"Aucun IRIS disponible", "RoofSun", Qgis.Info)
            return

        # sans cette entrée, le premier IRIS était pris d'office et la commune entière jamais analysée
        self.quartierCombo.addItem("Toute la commune", None)
        for iris in listeIris:
            self.quartierCombo.addItem(iris['nom'], iris)
        QgsMessageLog.logMessage(f"{len(listeIris)} IRIS chargés", "RoofSun", Qgis.Info)

    def resetCombosFrom(self, level: int):
        combos = [
            (self.departementCombo, False),
            (self.epciCombo, False),
            (self.communeCombo, False),
            (self.quartierCombo, False)
        ]

        for i in range(level-1, len(combos)):
            combo, enabled = combos[i]
            combo.clear()
            combo.setEnabled(enabled)

    def chargerCommunesParDepartement(self, codeDep: str):
        self.communeCombo.clear()
        data = self.apiGet(f"https://geo.api.gouv.fr/communes?codeDepartement={codeDep}&fields=nom,code")
        if not data:
            return

        self.communeCombo.addItem("Sélectionnez une commune...", None)
        for commune in data:
            if commune['code'] in self.EXCLUDED_COMMUNES:
                continue
            self.communeCombo.addItem(commune['nom'], commune['code'])

    def chargerCommunesParEpci(self, codeEpci: str):
        self.communeCombo.clear()
        data = self.apiGet(f"https://geo.api.gouv.fr/epcis/{codeEpci}/communes?fields=nom,code")
        if not data:
            return

        self.communeCombo.addItem("Sélectionnez une commune...", None)
        for commune in data:
            if commune['code'] in self.EXCLUDED_COMMUNES:
                continue
            self.communeCombo.addItem(commune['nom'], commune['code'])

    def getAllIris(self, codeInsee: str):
        listeIris = self.getIrisAvecBbox(codeInsee)
        if listeIris:
            listeIris.sort(key=lambda x: x['nom'])
            return listeIris

        QgsMessageLog.logMessage("Chargement complet des IRIS...", "RoofSun", Qgis.Info)
        listeIris = self.getIrisScanComplet(codeInsee)
        listeIris.sort(key=lambda x: x['nom'])
        return listeIris

    def getIrisAvecBbox(self, codeInsee: str):
        bbox = self.getBboxCommune(codeInsee)
        if not bbox:
            return []

        QgsMessageLog.logMessage(f"BBOX: {bbox}", "RoofSun", Qgis.Info)
        listeIris = []
        startIndex = 0

        while startIndex < self.MAX_IRIS_PER_COMMUNE:
            params = {
                'SERVICE': 'WFS', 'VERSION': '2.0.0', 'REQUEST': 'GetFeature',
                'TYPENAME': self.WFS_TYPENAME, 'BBOX': f"{bbox},EPSG:4326",
                'OUTPUTFORMAT': 'application/json', 'SRSNAME': 'EPSG:4326',
                'COUNT': self.BATCH_SIZE_BBOX, 'STARTINDEX': startIndex
            }

            response = requests.get(self.WFS_URL, params=params, timeout=self.WFS_TIMEOUT)
            if response.status_code != 200:
                break

            features = response.json().get('features', [])
            if not features:
                break

            listeIris.extend(self.extraireIrisDesFeatures(features, codeInsee))
            if len(features) < self.BATCH_SIZE_BBOX:
                break

            startIndex += self.BATCH_SIZE_BBOX

        return listeIris

    def getIrisScanComplet(self, codeInsee: str):
        QgsMessageLog.logMessage("Scan complet (20-30s)...", "RoofSun", Qgis.Info)
        listeIris = []
        startIndex = 0

        while True:
            params = {
                'SERVICE': 'WFS', 'VERSION': '2.0.0', 'REQUEST': 'GetFeature',
                'TYPENAME': self.WFS_TYPENAME, 'OUTPUTFORMAT': 'application/json',
                'SRSNAME': 'EPSG:4326', 'COUNT': self.BATCH_SIZE_FULL,
                'STARTINDEX': startIndex
            }

            response = requests.get(self.WFS_URL, params=params, timeout=self.WFS_TIMEOUT_LONG)
            if response.status_code != 200:
                break

            features = response.json().get('features', [])
            if not features:
                break

            QgsMessageLog.logMessage(f"Lot {startIndex // self.BATCH_SIZE_FULL + 1}: {len(features)} IRIS", "RoofSun", Qgis.Info)
            listeIris.extend(self.extraireIrisDesFeatures(features, codeInsee))

            if len(features) < self.BATCH_SIZE_FULL:
                break
            if startIndex > 100000:
                break

            startIndex += self.BATCH_SIZE_FULL

        return listeIris

    def extraireIrisDesFeatures(self, features, codeInsee: str):
        listeIris = []
        codesIrisVus = set()

        for feature in features:
            props = feature.get('properties', {})
            codeCom = self.getCodeCommuneDesProps(props)
            if codeCom != codeInsee:
                continue

            nomIris = props.get('nom_iris', '').strip()
            codeIris = props.get('code_iris', '').strip()
            typeIris = props.get('type_iris', '').strip()

            if not nomIris or not codeIris:
                continue
            if codeIris in codesIrisVus:
                continue

            codesIrisVus.add(codeIris)
            listeIris.append({
                'type': 'iris',
                'nom': self.formaterNomIris(nomIris, typeIris),
                'code': codeIris,
                'type_iris': typeIris,
                'source': 'WFS'
            })

        return listeIris

    def getCodeCommuneDesProps(self, props):
        for field in ['code_insee', 'depcom', 'insee_com', 'code_com']:
            codeCom = str(props.get(field, '')).strip()
            if codeCom and len(codeCom) == 5:
                return codeCom

        codeIrisFull = props.get('code_iris', '')
        if len(codeIrisFull) >= 5:
            return codeIrisFull[:5]

        return ''

    def getBboxCommune(self, codeInsee: str):
        data = self.apiGet(f"https://geo.api.gouv.fr/communes/{codeInsee}?fields=contour")
        if not data:
            return None

        geometry = data.get('contour')
        if not geometry:
            return None

        return self.calculerBboxDeGeometrie(geometry)

    def calculerBboxDeGeometrie(self, geometry):
        coords = []
        geomType = geometry.get('type')

        if geomType == 'Polygon':
            for ring in geometry.get('coordinates', []):
                coords.extend(ring)
        elif geomType == 'MultiPolygon':
            for poly in geometry.get('coordinates', []):
                for ring in poly:
                    coords.extend(ring)
        else:
            return None

        if not coords:
            return None

        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        return f"{min(lons)},{min(lats)},{max(lons)},{max(lats)}"

    def formaterNomIris(self, nomIris: str, typeIris: str = ''):
        nom = nomIris.strip()
        if nom.upper().startswith('IRIS '):
            nom = nom[5:]
        elif nom.upper().startswith('IRIS_'):
            nom = nom[5:]

        nomFormate = nom.title()
        if typeIris and typeIris not in ['H', 'A', 'D', 'Z']:
            nomFormate = f"{nomFormate} ({typeIris})"

        return f"IRIS {nomFormate}"

    def changementGti(self, index):
        self.selectedGtiLayer = None if index <= 0 else self.gtiComboBox.itemData(index)

    def getCodeCommuneSelect(self):
        return self.communeCombo.itemData(self.communeCombo.currentIndex())

    def getCoucheGtiSelect(self):
        return self.selectedGtiLayer

    def getQuartierSelect(self):
        if self.selectedIrisInArrondissement:
            return self.selectedIrisInArrondissement

        return self.quartierCombo.itemData(self.quartierCombo.currentIndex())


class DialogSelectionIris(QtWidgets.QDialog):

    def __init__(self, listeIris: List[Dict], nomArrond: str, parent=None):
        super().__init__(parent)
        self.listeIris = listeIris
        self.nomArrond = nomArrond
        self.irisSelect = None
        self.setWindowTitle(f"Sélectionner un IRIS - {nomArrond}")
        self.setMinimumWidth(400)
        self.setMinimumHeight(300)
        self.setModal(True)
        self.initUI()

    def initUI(self):
        layout = QtWidgets.QVBoxLayout()

        infoLabel = QtWidgets.QLabel(
            f"L'arrondissement {self.nomArrond} contient {len(self.listeIris)} IRIS.\n"
            "Veuillez sélectionner un IRIS spécifique :"
        )
        infoLabel.setWordWrap(True)
        layout.addWidget(infoLabel)

        self.listeWidgetIris = QtWidgets.QListWidget()
        self.listeWidgetIris.itemSelectionChanged.connect(self.quandSelectionChange)
        for iris in self.listeIris:
            item = QtWidgets.QListWidgetItem(iris['nom'])
            item.setData(Qt.ItemDataRole.UserRole, iris)
            self.listeWidgetIris.addItem(item)

        layout.addWidget(self.listeWidgetIris)

        layoutBoutons = QtWidgets.QHBoxLayout()

        boutonAnnuler = QtWidgets.QPushButton("Annuler")
        boutonAnnuler.clicked.connect(self.reject)
        layoutBoutons.addWidget(boutonAnnuler)

        self.boutonOk = QtWidgets.QPushButton("OK")
        self.boutonOk.clicked.connect(self.accepterSelection)
        self.boutonOk.setDefault(True)
        self.boutonOk.setEnabled(False)
        layoutBoutons.addWidget(self.boutonOk)

        layout.addLayout(layoutBoutons)

        self.setLayout(layout)

    def quandSelectionChange(self):
        self.boutonOk.setEnabled(len(self.listeWidgetIris.selectedItems()) > 0)

    def accepterSelection(self):
        itemsSelect = self.listeWidgetIris.selectedItems()
        if not itemsSelect:
            QtWidgets.QMessageBox.warning(self, "Sélection requise", "Veuillez sélectionner un IRIS.")
            return

        self.irisSelect = itemsSelect[0].data(Qt.ItemDataRole.UserRole)
        self.accept()

    def getIrisSelect(self):
        return self.irisSelect