# RENGLO SYSTEM



## Architecture (Multiple repositories)

```
Root
│
├── system/                     ← Core System (not to be edited)
│   ├── env_config.py           ← System configuration
│   ├── main.py                 ← Application Point of Entry
│   ├── wsgi.py                 ← Production WSGI entry point
│   ├── requirements.txt        ← System dependencies
│   └── README.md
│
|
├── console/                    ← Frontend (React + Vite)
|   ├── package.json            ← Workspace root
|   │   └── workspaces: [".", "../extensions/*/ui"]
|   ├── vite.config.ts          ← Vite configuration
|   ├── tsconfig.json           ← TypeScript config
|   ├── src/
|   │   ├── main.tsx
|   │   ├── router.tsx
|   │   ├── nav.tsx
|   │   ├── components/
|   │   └── contexts/
|   └── public/
|
│
├── extensions/                 ← Pluggable Extensions
│   ├── extension_x/
│   │   ├── README.md
│   │   ├── blueprints/         ← Data declarations for extension_x
│   │   ├── installer/          ← Setup scripts for extension_X
│   │   ├── package/            
│   │   │   ├── setup.py
│   │   │   ├── pyproject.toml
│   │   │   ├── requirements.txt
│   │   │   └── enerclave/
│   │   │       ├── __init__.py
│   │   │       └── handlers/  ← Handlers for extension_x
│   │   └── ui/                
│   │       ├── package.json   ← UI Dependencies for extension_x
│   │       ├── components/    ← Custom components for extension_x
│   │       ├── navigation/    ← Navigation components for extension_x
│   │       ├── onboarding/    ← Onboarding components for extension_x
│   │       └── pages/         ← Subsection components for extension_x
│   │
│   ├── extension_y/            ← Same structure
│   ├── schd/                   ← Same structure
│   └── data/                   ← Same structure
│
└── dev/                       ← Core Libraries (only for development)
   ├── renglo-api/             ← Renglo API (Flask routes)
   │   ├── renglo_api/
   │   │   ├── app.py          ← Flask APP declaration
   │   │   ├── routes/         ← System routes
   │   │   └── config.py       ← Config functions (not a config file)
   │   └── requirements.txt
   │
   └── renglo-lib/             ← Renglo Library (System Logic)
       ├── renglo/
       │   ├── app_auth/       ← Authentication subsystem
       │   ├── app_blueprint/  ← Blueprints subsystem
       │   ├── app_chat/       ← Authentication subsystem
       │   ├── app_data/       ← Data subsystem
       │   ├── app_docs/       ← Docs subsystem
       │   ├── app_schd/       ← Scheduler subsystem
       │   └── app_state/      ← State subsystem
       └── setup.py
```

```
Dependencies Flow:
┌─────────────────────────────────────────────────────────────────┐
│ system/ (Backend)                                               │
│   └── imports: renglo_api                                       │
│        └── imports: renglo-lib                                  │
│             └── uses: extensions/*/package/* (handlers)         │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ console/ (Frontend)                                             │
│   └── dynamically loads: @extensions/*/ui/*                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```


## INSTALLATION

Setting up a new development environment


Step 0. 

Create a project folder in your computer to hold the project folders.
The name doesn't affect the configuration. You can change it later.
You can move this folder around to different locations in your file system.
```
mkdir <NAME-OF-PROJECT>
cd <NAME-OF-PROJECT>
```

Step 1. 
Clone the System and the Console in it. Install its dependencies

```
git clone https://github.com/renglo/system.git
git clone https://github.com/renglo/console.git

```

Install the system dependencies
```
cd system
python3.12 -m venv venv
source venv/bin/activate
```

Install the console dependencies
```
cd ..
cd console
npm install
```

Step 2. 

Create a folder called /dev on the root of the project and clone the core libraries in it.

```
cd ..
mkdir dev
cd dev
git clone https://github.com/renglo/renglo-lib.git
git clone https://github.com/renglo/renglo-api.git
```

Install them in your local venv
```
# located in /dev
pip install -e renglo-lib
pip install -e renglo-api
```



Step 3.

Insert the provided* config files and start the system and console
(*) A system admin should have provided the config files to you.

Place env_config.py in the /system folder
Place .env.development and .env.production in the /console folder


Copy run.sh.TEMPLATE to run.sh
```bash
# Copy the run script template
cp system/run.sh.TEMPLATE system/run.sh

# Edit with your AWS profile and region
nano run.sh
```

Example `run.sh`:

```bash
#!/bin/bash
export AWS_PROFILE=my-profile
export AWS_DEFAULT_REGION=us-east-1

python main.py
```

## Running the System

### Local Development


Step 4. Setup the System Logo


Create two images. 

A small one (500x500 px, Max 100Kb, name: small_logo.jpg) for the Menu header and 
A large one (1000x1000 px, Max 500kb, name: large_logo.jpg) for the log-in page

Place both images in console/public 



## EXTENSIONS

Up to this point you have the bare bones version of the system.
If you want to use, edit and view the specialized extensions, you need to install them.


Step 5. 

Installing the base extensions (locally)

Create a folder called 'extensions' on the root of the project
```
mkdir extensions
cd extensions
```

Clone the system extensions  (schd, data, pes) 

```
git clone https://github.com/renglo/schd.git
git clone https://github.com/renglo/data.git
git clone https://github.com/renglo/pes.git
```

Install the system extensions
```
cd extensions
pip install -e schd/package
pip install -e pes/package

```

Install the extension blueprints

# if you are in extensions/
python schd/installer/upload_blueprints.py <env> --aws-profile <profile> --aws-region <region>
python pes/installer/upload_blueprints.py <env> --aws-profile <profile> --aws-region <region>

#python schd/installer/upload_blueprints.py renglo --aws-profile maker  --aws-region us-east-1
#python pes/installer/upload_blueprints.py renglo --aws-profile maker --aws-region us-east-1


Step 5b.

Installing custom extensions UI

Clone the extension code (in /extensions)
```
git clone https://some-url-where-repository-is-hosted/some-extension.git
```

Installing the handlers

If you want to install the handlers, consult /extensions/<extension_name>/service/README.md

(Optional) if you want to give the user the option to install the extension in their portfolio (in the 'account_settings' section) do the following.
```
# Open the console config files (.env.development and .env.production) 
# Add the name of the extension to VITE_EXTENSIONS (it is a comma separated string)

```

Repeat Step 5 for each one of the extensions you need to install to the system. 

Notes: 
- Installing an extension in the system doesn't make it immediately available to the user
- Follow the README.md in each extension folder to understand how to activate it.





## RUNNING THE SYSTEM



Initialize the backEnd (system)
```
cd system
source venv/bin/activate
source run.sh
```

Initialize the console (in another terminal)
```
cd console
npm run dev
```




## AVAILABLE SYSTEM ROUTES

The system offers a lot of out of the box functionality:

- `/_auth/*` - Authentication endpoints
- `/_data/*` - Data management endpoints
- `/_chat/*` - Chat functionality
- `/_blueprint/*` - Blueprint management
- `/_docs/*` - Document management
- `/_schd/*` - Scheduler endpoints (calls extension handlers)
- `/_state/*` - State management
- `/ping` - Health check
- `/time` - Current time (authenticated)

Visit `http://localhost:5001/ping` to verify the application is running.



