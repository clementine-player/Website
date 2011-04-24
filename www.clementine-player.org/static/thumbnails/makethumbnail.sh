#!/bin/sh

large=`basename $1`
small=`echo $large | sed 's/\.png/t.png/'`

convert -scale 440x440 $1 $large
convert -scale 300x300 $1 $small
