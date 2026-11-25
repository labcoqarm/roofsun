"""RoofSun : modèle Processing qui filtre les toitures et calcule leur indice de potentiel solaire."""

from qgis.core import Qgis, QgsProcessing
from qgis.core import QgsProcessingAlgorithm
from qgis.core import QgsProcessingMultiStepFeedback
from qgis.core import QgsProcessingParameterVectorLayer
from qgis.core import QgsProcessingParameterRasterLayer
from qgis.core import QgsProcessingParameterFeatureSink
import processing


class Roofsun(QgsProcessingAlgorithm):

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterVectorLayer('btiment', 'Bâtiment', types=[Qgis.ProcessingSourceType.VectorPolygon], defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer('zone', "Zone d'étude", types=[Qgis.ProcessingSourceType.VectorPolygon], defaultValue=None))
        self.addParameter(QgsProcessingParameterRasterLayer('global_tilted_irradiance_gti', 'Global Tilted Irradiance (GTI)', defaultValue=None))
        self.addParameter(QgsProcessingParameterFeatureSink('IndiceToiture', 'Indice toiture', type=Qgis.ProcessingSourceType.VectorAnyGeometry, createByDefault=True, supportsAppend=True, defaultValue='TEMPORARY_OUTPUT'))

    def processAlgorithm(self, parameters, context, model_feedback):
        feedback = QgsProcessingMultiStepFeedback(11, model_feedback)
        results = {}
        outputs = {}

        alg_params = {
            'INPUT': parameters['btiment'],
            'INTERSECT': parameters['zone'],
            'PREDICATE': [0],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['ExtractBatiZone'] = processing.run('native:extractbylocation', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

        # extraction et non sélection : une sélection n'est pas transmise à l'étape suivante
        alg_params = {
            'EXPRESSION': '"NATURE" IN (\'Indifférenciée\', \'Industriel, agricole ou commercial\')',
            'INPUT': outputs['ExtractBatiZone']['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['SelectionTypeBati'] = processing.run('native:extractbyexpression', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}

        alg_params = {
            'FIELD_LENGTH': 20,
            'FIELD_NAME': 'inclinaison_dgr',
            'FIELD_PRECISION': 20,
            'FIELD_TYPE': 0,
            'FORMULA': 'degrees(atan(("Z_MAX_TOIT" - "Z_MIN_TOIT") / sqrt(area($geometry))))',
            'INPUT': outputs['SelectionTypeBati']['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['CdcInclinaison'] = processing.run('native:fieldcalculator', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(3)
        if feedback.isCanceled():
            return {}

        alg_params = {
            'EXPRESSION': '"inclinaison_dgr" <= 45',
            'INPUT': outputs['CdcInclinaison']['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['FiltreInclinaison'] = processing.run('native:extractbyexpression', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(4)
        if feedback.isCanceled():
            return {}

        alg_params = {
            'FIELD_LENGTH': 20,
            'FIELD_NAME': 'surfDisp',
            'FIELD_PRECISION': 20,
            'FIELD_TYPE': 0,
            'FORMULA': 'area($geometry) * 0.7',
            'INPUT': outputs['FiltreInclinaison']['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['CdcSurfaceDisponible'] = processing.run('native:fieldcalculator', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(5)
        if feedback.isCanceled():
            return {}

        alg_params = {
            'EXPRESSION': '"surfDisp" >= 1.7',
            'INPUT': outputs['CdcSurfaceDisponible']['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['FiltreSurfaceDisponible'] = processing.run('native:extractbyexpression', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(6)
        if feedback.isCanceled():
            return {}

        alg_params = {
            'FIELD_LENGTH': 20,
            'FIELD_NAME': 'compacite',
            'FIELD_PRECISION': 20,
            'FIELD_TYPE': 0,
            'FORMULA': 'perimeter($geometry) / (2 * sqrt(pi() * area($geometry)))',
            'INPUT': outputs['FiltreSurfaceDisponible']['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['CdcCompacite'] = processing.run('native:fieldcalculator', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(7)
        if feedback.isCanceled():
            return {}

        alg_params = {
            'EXPRESSION': '"compacite" < 1.4',
            'INPUT': outputs['CdcCompacite']['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['FiltreCompacite'] = processing.run('native:extractbyexpression', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(8)
        if feedback.isCanceled():
            return {}

        alg_params = {
            'FIELD_LENGTH': 20,
            'FIELD_NAME': 'scoreOrientation',
            'FIELD_PRECISION': 20,
            'FIELD_TYPE': 0,
            # main_angle donne l'axe long en degrés : axe est-ouest (pans nord et sud) = 1, axe nord-sud = 0
            'FORMULA': 'round(abs(sin(radians(main_angle($geometry)))), 6)',
            'INPUT': outputs['FiltreCompacite']['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['CdcScoreOrientation'] = processing.run('native:fieldcalculator', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(9)
        if feedback.isCanceled():
            return {}

        alg_params = {
            'COLUMN_PREFIX': 'GTI',
            'INPUT': outputs['CdcScoreOrientation']['OUTPUT'],
            'INPUT_RASTER': parameters['global_tilted_irradiance_gti'],
            'RASTER_BAND': 1,
            'STATISTICS': [2],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['StatistiquesDeZoneGti'] = processing.run('native:zonalstatisticsfb', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(10)
        if feedback.isCanceled():
            return {}

        alg_params = {
            'FIELD_LENGTH': 30,
            'FIELD_NAME': 'indice',
            'FIELD_PRECISION': 30,
            'FIELD_TYPE': 2,
            'FORMULA': '''CASE
  WHEN "GTImean" IS NULL THEN NULL
  WHEN "GTImean" > 5.0 AND "scoreOrientation" >= 0.85 THEN 'Très élevé'
  WHEN "GTImean" > 4.2 AND "scoreOrientation" >= 0.7 THEN 'Élevé'
  WHEN "GTImean" >= 3.0 AND "scoreOrientation" >= 0.3 THEN 'Moyen'
  WHEN "GTImean" >= 3.0 OR "scoreOrientation" >= 0.3 THEN 'Faible'
  ELSE 'Très faible'
END''',
            'INPUT': outputs['StatistiquesDeZoneGti']['OUTPUT'],
            'OUTPUT': parameters['IndiceToiture']
        }
        outputs['CdcIndice'] = processing.run('native:fieldcalculator', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        results['IndiceToiture'] = outputs['CdcIndice']['OUTPUT']
        return results

    def name(self):
        return 'RoofSun'

    def displayName(self):
        return 'RoofSun'

    def group(self):
        return ''

    def groupId(self):
        return ''

    def createInstance(self):
        return Roofsun()
