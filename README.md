# rgb_drone_canopy_cover

## YAML File
### Files
Files are used to indicate the path to required files.
* [files]
    * [dates_dir] | The path to the directory that containes all the directories from different scan dates
    * [geojson_path] | The path to the geojson file
    * [plots_dir_name] | The name of the directory for the plots to be saved in
    * [csv_name] | The name of the output csv file

### Tif info
Information about the TIF files.
* [tif_info]
    * [common_espg] | The common ESPG to be used

### Image correction
Used when there needs to be image correction done
* [image_correction]
    * [image_rotated] | set to True if images need to be set straight, False if not


### Color
Color information for masking
* [color]
    * [lower] | lower bound of the hsv value for green, should be in array format, ex. [0, 0, 0]
    * [upper] | upper bound of the hsv value for green, should be in array format, ex. [0, 0, 0]


## Command line arguments
* Required
  * -y, --yaml | YAML file to use for processing
* Optional
  * -v, --verbose | Turn on verbose mode to print to stdout while processing


