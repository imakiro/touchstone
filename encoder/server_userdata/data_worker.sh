#!/bin/bash

RAX_USERNAME=$1
RAX_APIKEY=$2
DATA_MASTER_IP=$3
MYSQL_PASS=$4
BRANCH=$5

sudo apt-get update
sudo apt-get install git -y
git clone https://github.com/metral/touchstone.git ~/touchstone

cd ~/touchstone/encoder/data_worker

if [ "$BRANCH" != "master" ]; then
    git checkout -b $BRANCH origin/$BRANCH
fi

./install.sh $RAX_USERNAME $RAX_APIKEY $DATA_MASTER_IP $MYSQL_PASS
