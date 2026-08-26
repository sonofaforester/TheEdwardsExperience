# The Edwards Experience

This app stores its data in a local JSON file you choose. The browser writes changes directly to that file; no Python server or database is required.

## Run it

Open `index.html` using a current version of Chrome or Edge. The first time, choose an existing JSON file or create a new one. The app securely remembers that file in browser storage and restores it on later refreshes. Keep the file somewhere backed up, such as in OneDrive.

The browser asks permission to access the selected file. Changes save automatically after every edit. If browser permission expires, select **Reconnect saved file**—you will not need to browse for the file again.

The reset button replaces the selected file's contents with the sample workspace.

## Routes

The app uses hash routes, so its current page remains available after a refresh:

- `#/` — Overview
- `#/people` — People
- `#/people/<employee-id>` — An employee's 1:1 history
- `#/people/<employee-id>/1-on-1` — Start a 1:1 workspace
- `#/people/<employee-id>/1-on-1/<session-id>` — Edit a saved 1:1
- `#/agenda` — Team agenda
- `#/actions` — Action items
