from transform_function import *

column_mapping = {
    "filename": {"name": "sample_id", "type": "[t]", "transform": remove_extension},
    "particleId": {"name": "object_id", "type": "[f]", "transform": None},
    # "hasImage": {"name": "has_image", "type": "[t]", "transform": lambda v: "true" if v else "false"},
    "hasImage": {},

    # "instrument.name": {"name": "instrument", "type": "[t]", "transform": None},
    # "instrument.serialNumber": {"name": "serialnumber", "type": "[t]", "transform": None},

    "instrument.name": {"name": "acq_name", "type": "[t]", "transform": None},
    "instrument.serialNumber": {"name": "acq_id", "type": "[t]", "transform": None},


    "instrument.measurementSettings.name": {"name": "acq_measurementSettings_name", "type": "[t]", "transform": None},
    "instrument.measurementSettings.duration": {"name": "acq_measurementSettings_duration", "type": "[f]", "transform": None, "bioodv": {
        "object":"SDN:P01::AZDRZZ01",
        "units":"SDN:P06:UMIN"
    }},
    "instrument.measurementSettings.CytoSettings.SamplePompSpeed": {"name": "acq_measurementSettings_pumpSpeed", "type": "[f]", "transform": None},
    "instrument.measurementSettings.triggerChannel": {"name": "acq_measurementSettings_triggerChannel", "type": "[t]", "transform": None},
    "instrument.measurementSettings.triggerLevel": {"name": "acq_measurementSettings_triggerLevel", "type": "[f]", "transform": None},
    "instrument.measurementSettings.smartTrigger": {"name": "acq_measurementSettings_smartTrigger", "type": "[t]", "transform": lambda v: "true" if v else "false"},
    # "instrument.measurementSettings.takeImages": {"name": "measurementSettings_takeImages", "type": "[t]", "transform": None},
    # "instrument.measurementSettings.takeImages": {"name": None},

    "instrument.measurementResults.start": {"name": "sample_measurementResults_Start", "type": "[t]", "transform": extract_date_utc},
    "instrument.measurementResults.start*1": {"name": "sample_measurementResults_StartH", "type": "[t]", "transform": extract_time_utc},
    "instrument.measurementResults.duration": {"name": "sample_measurementResults_duration", "type": "[f]", "transform": None},
    "instrument.measurementResults.particleCount": {"name": "sample_measurementResults_particleCount", "type": "[f]", "transform": None},
    "instrument.measurementResults.particlesInFileCount": {"name": "sample_measurementResults_particlesInFileCount", "type": "[f]", "transform": None},
    "instrument.measurementResults.pictureCount": {"name": "sample_measurementResults_pictureCount", "type": "[f]", "transform": None},
    "instrument.measurementResults.pumpedVolume": {"name": "sample_measurementResults_pumpedVolume", "type": "[f]", "transform": None},
    "instrument.measurementResults.analysedVolume": {"name": "sample_measurementResults_analysedVolume", "type": "[f]", "transform": None},
    "instrument.measurementResults.particleConcentration": {"name": "sample_measurementResults_particleConcentration", "type": "[f]", "transform": None},
    "instrument.measurementResults.systemTemperature": {"name": "sample_measurementResults_systemTemperature", "type": "[f]", "transform": None},
    "instrument.measurementResults.sheathTemperature": {"name": "sample_measurementResults_sheathTemperature", "type": "[f]", "transform": None},
    "instrument.measurementResults.absolutePressure": {"name": "sample_measurementResults_absolutePressure", "type": "[f]", "transform": None},
    "instrument.measurementResults.differentialPressure": {"name": "sample_measurementResults_differential_pressure","type": "[f]","transform": None},

    # commented because same data are too long to be stored in the colunms (more than 250 characters (limited in Ecotaxa by varstring))
    # "particles[].pulseShapes*FWS": {"name": "object_pulseShape_FWS","type": "[t]","transform":search_pulse_shapes("FWS")},
    # "particles[].pulseShapes*FWS": {"name": "object_pulseShape_FWS","type": "[t]","transform":add_pulse_shapes("FWS")},
    # "particles[].pulseShapes*Sidewards_Scatter": {"name": "object_pulseShape_Sidewards_Scatter","type": "[t]","transform":search_pulse_shapes("Sidewards Scatter")},
    # "particles[].pulseShapes*Fl_Yellow": {"name": "object_pulseShape_Fl_Yellow","type": "[t]","transform":search_pulse_shapes("Fl Yellow")},
    # "particles[].pulseShapes*Fl_Orange": {"name": "object_pulseShape_Fl_Orange","type": "[t]","transform":search_pulse_shapes("Fl Orange")},
    # "particles[].pulseShapes*Fl_Red": {"name": "object_pulseShape_Fl_Red","type": "[t]","transform":search_pulse_shapes("Fl Red")},
    # "particles[].pulseShapes*Curvature": {"name": "object_pulseShape_Curvature","type": "[t]","transform":search_pulse_shapes("Curvature")},
    # "particles[].pulseShapes*Forward_Scatter_Left": {"name": "object_pulseShape_Forward_Scatter_Left","type": "[t]","transform":search_pulse_shapes("Forward Scatter Left")},
    # "particles[].pulseShapes*Forward_Scatter_Right": {"name": "object_pulseShape_Forward_Scatter_Right","type": "[t]","transform":search_pulse_shapes("Forward Scatter Right")},
}
