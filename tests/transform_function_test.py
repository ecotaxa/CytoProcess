from src.CytoProcess.transform_function import extract_commit_version

# Exemple d'utilisation :
chaine = "CytoUSB Version: Build: 'ReleaseWebsite' , Commit: CytoUsb-v6.3.2.2-0-g2cf62c7b4, User=rob@Tommie, Machine=TOMMIE, ProjectPath=C:\\Users\\rob\\Documents\\Git\\CytoSoftware\\CytoUSB\\+2cf62c7b455d69527060d522e6a238cd7abf3744"

commit = extract_commit_version(chaine)

assert commit == "CytoUsb-v6.3.2.2-0-g2cf62c7b4", f"Expected 'CytoUsb-v6.3.2.2-0-g2cf62c7b4', got '{commit}'"

