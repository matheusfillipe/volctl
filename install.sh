#!/bin/sh

sudo pip install .
sudo cp data/apps.volctl.gschema.xml /usr/share/glib-2.0/schemas/
sudo update-desktop-database
sudo glib-compile-schemas /usr/share/glib-2.0/schemas/
