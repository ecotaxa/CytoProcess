"""
import to ecotaxa
"""

import json
import os
import argparse
import getpass
from pathlib import Path
import requests # pip install requests
from urllib.parse import urlencode # standard lib


userfile = None

def save_user(user):
    print("save_user")
    # if userfile != None and user['overwriteUser']:
    if userfile != None and user['overwriteCfg']:
        print("Saving...")
        with open(userfile, 'w') as f:
            json.dump(user, f, indent=4)

def login(user):
    print("login")

    if 'token' in user:
        return user

    body = {
	    "password": user['password'],
	    "username": user['username']
    }
    
    url =  f"{user['ecotaxa']}/api/login"
    response = requests.post(url, json=body)

    print("response", response)

    if response.status_code == 200:
        # user['token'] = response.json()['token']
        token = response.json()
        print("token", token)
        user['token'] = token
        if user['overwriteUser']:
            user.pop('password') # no need anymore
        save_user(user)

        print("Login successful")

        return user
    else:
        raise Exception("Login failed")

def printUser(user):
    if 'password' in user:
        copiedUser = user.copy()
        copiedUser['password'] = "******"
        print("User", json.dumps(copiedUser, indent=4, sort_keys=True))       
        return
    
    print("User", json.dumps(user, indent=4, sort_keys=True))

def getHeader(user,contentType="application/json"):
    
     return {
        "Authorization": "Bearer " + user['token'],
        "Content-Type": contentType,
        "accept" : "application/json"
     }

def searchProject(user, project):
    print("searchProject")
    header = getHeader(user)
    print("header", header)
    # print("project:",project)
    # encoded_string=urlencode(str(project))
    # print("encoded_string", encoded_string)
    # url = f"{user['ecotaxa']}/api/projects/search?title_filter={encoded_string}"
    url = f"{user['ecotaxa']}/api/projects/search?title_filter={project}"

    print("url", url)
    # print("encoded",urlencode(url))

    response = requests.get(url, headers=header)

    print("response", response)
    projectList = response.json()
    print("project list", json.dumps(projectList, indent=4, sort_keys=True))

    return projectList

def getProjectFromID(user):
    print("getProjectFromID")
    if not 'projectid' in user:
        return None

    header = getHeader(user)
    print("header", header)
    url = f"{user['ecotaxa']}/api/projects/{user['projectid']}"

    response = requests.get(url, headers=header)

    if response.status_code == 200:
        project = response.json()
        print("project", json.dumps(project, indent=4, sort_keys=True))
        return project
    else:
        raise Exception(f"Project with ID: {user['projectid']} not found")


def getProject(user, project):
    print("getProject")
    header = getHeader(user)
    print("header", header)
    url = f"{user['ecotaxa']}/api/projects/{project}"
    print("url", url)
    response = requests.get(url, headers=header)
    print("response", response)
    if response.status_code == 200:
        project = response.json()
        print("project", json.dumps(project, indent=4, sort_keys=True))
        return project
    else:
        raise Exception(f"Project with ID: {project} not found")

def is_numeric(value):
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False
    
def createProject(user, project):
    print("createProject")

    if is_numeric(project):
        raise Exception(f"Project is numeric not a string")

    header = getHeader(user)
    print("header", header)
    url = f"{user['ecotaxa']}/api/projects/create"
    print("url", url)

    body = {
        "title": project, #user['project'],
        "visible": True
        }
    
    if 'instrument' in user:
        body['instrument'] = user['instrument']


    print("body", body)
    
    body = json.dumps(body)
    print("body", body)

    response = requests.post(url, json=body, headers=header)
    print("response", response)

    match (response.status_code):
        case 200:
            project = response.json()
            print("project", json.dumps(project, indent=4, sort_keys=True))
            return project
        case 409:
            raise Exception(f"Project already exists")
        case 404:
            raise Exception(f"Cannot connect to the ecotaxa server {url}")
        case 422:
            raise Exception(f"Cannot create project: {response.json()}")
        case _:
            raise Exception(f"Cannot create project: {response.json()}")

def upload_file_with_users_files(user, zip_file):
    header = {
        "Authorization": "Bearer " + user['token'],
        "accept": "application/json"
    }
    
    url = f"{user['ecotaxa']}/api/users_files"

    print("uploading file...")
    with open(zip_file, 'rb') as f:
        files = {
            'file': (Path(zip_file).name, f, 'application/zip'),
            'path': (None, '')
        }
        response = requests.post(url, headers=header, files=files)
    
        match (response.status_code):
            case 200:
                upload = response.json()
                print("upload url", upload)
                return upload
            case 403:
                print("reponse:", response.json())
                raise Exception(f"Cannot connect to the ecotaxa server. Access forbidden")
            case 404:
                print("reponse:", response.json())
                raise Exception(f"Cannot connect to the ecotaxa server {url}")
            case _:
                print("reponse:", response.json())
                raise Exception(f"Cannot upload file: {response.json()}")

def upload_file(user, zip_file):
    header = {
        "Authorization": "Bearer " + user['token'],
        "accept": "application/json"
    }
    
    url = f"{user['ecotaxa']}/api/my_files/"

    print("uploading file...")
    with open(zip_file, 'rb') as f:
        files = {
            'file': (Path(zip_file).name, f, 'application/zip'),
            # 'path': (None, '/tmp/myfile.zip'),  # Set specific path value
            'path': (None, ''),

            'tag': (None, '')
        }
            # 'path': (None, ''),
            # 'tag': (None, "import")
        response = requests.post(url, headers=header, files=files)
    
        match (response.status_code):
            case 200:
                # upload = response.json()
                upload = response.json()
                print("upload url", upload)
                return upload
            case 403:
                print("reponse:", response.json())
                raise Exception(f"403 - Cannot connect to the ecotaxa server. Access forbidden")
            case 404:
                print("reponse:", response.json())
                raise Exception(f"404 - Cannot connect to the ecotaxa server {url}")
            case _:
                # print("reponse:", response.text())
                raise Exception(f"{response.status_code} - Cannot upload file: {response.json()}")

    raise Exception(f"Cannot upload file: issue with {zip_file}")

def upload_file_(user,zip_file):
    print("upload_file")

    # header = getHeader(user,"multipart/form-data")
    # header = getHeader(user)
    # header = {
    #    "Authorization": "Bearer " + user['token'],
        # "accept": "application/json"
# }
    # header = {
    #     "Authorization": "Bearer " + user['token'],
    #     "Content-Type": "multipart/form-data",
    #     "accept" : "application/json"
    #  }
    header = getHeader(user,"multipart/form-data")

    print("header", header)

    # url = f"{user['ecotaxa']}/api/my_files/"
    url = f"{user['ecotaxa']}/api/user_files/"
    print("url", url)

    # data = {
    #     "path" : "" , #zip_file,
    #     "tag" :  "" , #"import_test"
    # }
    # data = json.dumps(data)
    # print("data", data)

    print("uploading file...")
    # with open(zip_file, "rb") as file:
    #     files = {"file": file}
    # files = {"file": open(zip_file, "rb")}
    # response = requests.post(url, files=files , headers=header , json=data)
    with open(zip_file, 'rb') as f:
        # files = {
            # "file": (os.path.basename(zip_file), f), 
            # "path":"",
            # "tag":"import_test"
        # }

        # path = Path(zip_file).absolute().as_posix()
        zippath = Path(zip_file).resolve().as_posix()
        print("zippath", zippath)
        # path = Path("/",os.path.basename(zip_file)).as_posix()
        path = Path('toto').as_posix()
        print("path", path)
        files = {
            # "file": (os.path.basename(zip_file), f, "application/zip"),
            "file": (os.path.basename(zippath), f, "application/zip"),
            "path": path, #os.path.basename(zip_file), #Path(zip_file).parent.as_posix(), #None, #(None, zip_file),
            # "tag": None #(None, 'import_test')
        }
        # files = json.dumps(files)
        print("files", files)
        # response = requests.post(url, headers=header, files=files, json=data)
        response = requests.post(url, headers=header, files=files)#, json=data)

    # response = requests.post(url, files=files, data=data)
    # files["file"].close()  # Close the file after the request

        print("response", response)

        match (response.status_code):
            case 200:
                upload = response.json()
                print("upload url", upload)
                return upload
            case 403:
                print("reponse:", response.json())
                raise Exception(f"Cannot connect to the ecotaxa server. Access forbidden")
            case 404:
                print("reponse:", response.json())
                raise Exception(f"Cannot connect to the ecotaxa server {url}")
            case _:
                print("reponse:", response.json())
                raise Exception(f"Cannot upload file: {response.json()}")


def import_zip_file(user, zip_file, skip_loaded_files=False, skip_existing_objects=False, update_mode=False):
    print("import_zip_file:", zip_file)

    header = getHeader(user)
    print("header", header)

    url = f"{user['ecotaxa']}/api/file_import/{user['projectid']}"
    print("url", url)

    body = {
        "source_path": zip_file, #"/import_test.zip",
        "skip_loaded_files": True if skip_loaded_files else False,
        "skip_existing_objects": True if skip_existing_objects else False,
        "update_mode": 'YES' if update_mode else ""
    }
    
    # body = json.dumps(body)
    # print("body", body)

    response = requests.post(url, json=body, headers=header)
    print("response", response)

    match (response.status_code):
        case 200:
            project = response.json()
            print("project", json.dumps(project, indent=4, sort_keys=True))
            return project
        case 404:
            raise Exception(f"404 - Cannot find the project {user['projectid']}")
        case 422:
            raise Exception(f"422 - Cannot import project: {response.json()}")
        case _:
            raise Exception(f"{response.status_code} - Cannot import project: {response.json()}")


# ########################################
def main(user, zip_file):
     
    try:
        login(user)

        printUser(user)

        # searchProject(user, project)
        if 'projectid' in user:
            project = getProject(user, project)
    
        else:
            if 'project' in user:
                projectList = searchProject(user, user['project'])
                match len(projectList):
                    case 0:
                        project = createProject(user, user['project'])
                        print("project",project)
                        user['projectid']=project['projid']
                        printUser(user)
                        save_user(user)
                    case 1:
                        project = projectList[0]
                        print("project",project)
                        user['projectid']=project['projid']
                        printUser(user)
                        save_user(user)
                    case _:
                        raise Exception("You have several project with the same name, please add the projectid feature in user.json file")
            else:
                raise Exception("You need to specify a project")


            uploaded = upload_file(user, zip_file)
            print("uploaded", uploaded)
            import_zip_file(user, uploaded, False, False, update_mode=True)

        exit(1)
    except Exception as e:
        print(str(e))  # Simple message

        print("------- Full message -------")
        print(repr(e)) # More detailed representation

        # DEBUG Mode
        print("------- Full traceback -------")
        import traceback
        print(traceback.format_exc())

        exit(0)


#########################################
# CLI
if __name__ == "__main__":

    print("-- import.py --")

    parser = argparse.ArgumentParser(description="Import Cytosense data to Ecotaxa")

    parser.add_argument("--config", help="The config file to connect to Ecotaxa")
    parser.add_argument("--zip", help="The zip file to import")
    parser.add_argument("--project", help="The project ID to import the data")
    parser.add_argument("--ecotaxa", default="https://ecotaxa.obs-vlfr.fr", help="The Ecotaxa url")
    parser.add_argument("--overwriteUser", default=False, help="Overwrite the user config file (remove password)")
    parser.add_argument("--overwriteCfg", default=False, help="Overwrite the config file (don't erase password if present)")

    args = parser.parse_args()

    config = args.config
    zip_file = args.zip
    

    ecotaxa = args.ecotaxa

    if config != None:
        userfile = config
        # read the configuration file
        with open(userfile, "r") as f:
            user = json.load(f)
            user['ecotaxa'] = ecotaxa # overwrite with parameter

    if not 'username' in user:
        user['username'] = input("Enter user: ")

    if not 'password' in user:
        user['password'] = getpass("Enter password: ")

    print(f"User: {user}")


    if args.project != None:
        if is_numeric(args.project):
            user['projectid']=float(args.project)
        else:
            project = args.project
            user['project']=project


    if zip_file == None:
        zip_file = input("Enter zip file: ")
    print(f"Zip file: {zip_file}")


    overWriteUser = args.overwriteUser
    #overwrite user force to overwrite the config file
    overWriteCfg = args.overwriteCfg | overWriteUser
    user['overwriteUser'] = overWriteUser
    user['overwriteCfg'] = overWriteCfg

    if project == None  and not 'projectid' in user:
        project = input("Enter project: ")
        if is_numeric(project):
            user['projectid']=float(project)
        else:
            user['project']=project
    print(f"Project: {project}")

    main (user, zip_file)

