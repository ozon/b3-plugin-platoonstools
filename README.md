# PlatoonTools Plugin for [B3](http://www.bigbrotherbot.net/ "B3")
This plugin fetches platoon information from Battlelog.
B3 now knows clan members and can, for example, automatically assign groups.

### Features

- detect platoon members and setup client groups
- Supports multiple platoons


## Usage

### Installation
1. Copy the file [extplugins/platoontools.py](extplugins/platoontools.py) into your `b3/extplugins` folder and
[extplugins/conf/plugin_platoontools.ini](extplugins/conf/plugin_platoontools.ini) into your `b3/conf` folder

2. Add the following line in your b3.xml file (below the other plugin lines)
```xml
<plugin name="platoontools" config="@conf/plugin_platoontools.ini"/>
```

### Settings and Messages
Edit the `plugin_platoontools.ini` file and add the platoon ID.
