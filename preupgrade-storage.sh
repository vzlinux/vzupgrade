#!/bin/bash

#
# Copyright (c) 2017-2019 Virtuozzo International GmbH. All rights reserved.
#
# Our contact details: Virtuozzo International GmbH, Vordergasse 59, 8200
# Schaffhausen, Switzerland.
#

SOURCE="pstorage"
DEST="vstorage"

STORAGE_LIBEXEC="/usr/libexec"
STORAGE_ETC="/etc"
STORAGE_LOG="/var/log"
STORAGE_LIB="/var/lib"

rename_path()
{
	local path="$1"

	if [ -d "$path/$SOURCE" ] && [ ! -d "$path/$DEST" ]; then
		mv "$path/$SOURCE" "$path/$DEST"
		ln -s "$path/$DEST" "$path/$SOURCE"
	fi
}

rename_storage_dirs()
{
	rename_path $STORAGE_LIBEXEC
	rename_path $STORAGE_ETC
	rename_path $STORAGE_LOG
	rename_path $STORAGE_LIB
}

stop_all_services()
{
	service pstorage-csd stop >/dev/null 2>&1
	service pstorage-mdsd stop >/dev/null 2>&1
}

stop_all_services
rename_storage_dirs
