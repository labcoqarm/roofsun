"""RoofSun : point d'entrée lu par QGIS au chargement du plugin."""


def classFactory(iface):
    from .RoofSun import RoofSun
    return RoofSun(iface)
