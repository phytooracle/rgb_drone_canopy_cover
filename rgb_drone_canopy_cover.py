import sys
import numpy as np
import pandas as pd
import geopandas
import fiona
import rasterio
import rasterio.mask
import json
import cv2
import glob
import os
import yaml
import argparse
import matplotlib.pyplot as plt


from plantcv import plantcv as pcv
from PIL import Image
from matplotlib.colors import hsv_to_rgb


def get_args():
    """
    Get command-line arguments
    """

    parser = argparse.ArgumentParser(
        description='PhytoOracle | Scalable, modular phenomic data processing pipelines',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('-y',
                        '--yaml',
                        help='YAML file specifying processing tasks/arguments',
                        metavar='str',
                        type=str,
                        required=True)

    return parser.parse_args()


def get_all_directories():
    """
    Returns the list of scan-date directories.
    """
    dates_dir = dictionary['files']['dates_dir']
    return glob.glob(os.path.join(dates_dir, "*", "*.tif"), recursive=True)


def read_geojson():
    """
    """
    geojson_path = dictionary['files']['geojson_path']
    common_espg = dictionary['tiff_info']['common_espg']

    # Read in the geoJSON file to a geopandas data frame
    gdf = geopandas.read_file(geojson_path)

    # Transform CRS
    gdf = gdf.to_crs(common_espg)

    return gdf


def create_dataframe():
    """
    """
    return pd.DataFrame(columns=["Date", "ID", "Percentage"])


def crop_plot(gdf, id, src, plots_directory):
    """
    """
    # Get the row of that plot by id and convert to json
    a = gdf[gdf['id'] == id].to_json()

    # Load json object
    json_object = json.loads(a)

    # Create shape list
    shape = [json_object['features'][0]['geometry']]

    out_image, out_transform = rasterio.mask.mask(src, shape, crop=True)
    out_meta = src.meta

    # Save the resulting raster  
    out_meta.update({"driver": "GTiff",
                    "height": out_image.shape[1],
                    "width": out_image.shape[2],
                    "transform": out_transform})

    # Save plot image to plots_directory by id
    with rasterio.open(plots_directory + f"plot_{id}.tif", "w", **out_meta) as dest:
        dest.write(out_image)


def rotate_plot(plots_directory, id):
    """
    """
    img, path, filename = pcv.readimage(filename = plots_directory + f"plot_{id}.tif")
    row, col, offset = 0, 0, 1
    black = np.zeros((1,3), dtype = np.int8)

    for i in range(len(img[0])):
        if not np.array_equal(img[offset][i], black[0]):
            col = i
            break

    for j in range(len(img)):
        if not np.array_equal(img[j][offset], black[0]):
            row = j
            break

    ratio = (col - offset)/(row - offset)
    angle = np.arctan(ratio) * 180 / np.pi

    input_image = Image.open(plots_directory + f"plot_{id}.tif")

    # rotate image
    output = input_image.rotate(angle)

    im2 = output.crop(output.getbbox())
    im2.save(plots_directory + f"plot_{id}_rotated_cropped.tif")
    im2.save(plots_directory + f"plot_{id}_rotated_cropped.png")


def mask_image(image_name):
    """
    """
    lower = tuple(dictionary['color']['lower'])
    upper = tuple(dictionary['color']['upper'])


    image = cv2.imread(image_name)
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    
    hsv_image = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
    
    mask = cv2.inRange(hsv_image, lower, upper)
    
    result = cv2.bitwise_and(image, image, mask=mask)
    
    result[np.where((result==[0,0,0]).all(axis=2))] = [255,255,255]

    return result


def get_pixel_percent(image, total_pixel):
    """
    """
    # Count non-white pixels.
    white = np.array([255, 255, 255])
    
    count, total = 0, 0
    for i in range(len(image)):
        for j in range(len(image[0])):
            if not np.array_equal(white, image[i][j]):
                count += 1
            total += 1

    # calculate percentage, the total pixels are determined by the first image's size
    percent = count/total_pixel*100

    return percent


def write_to_file(df):
    """
    """
    dates_dir = dictionary['files']['dates_dir']
    csv_name = dictionary['files']['csv_name']
    df.to_csv(dates_dir + "/" + csv_name)


def main():

    args = get_args()

    with open(args.yaml, 'r') as stream:
        global dictionary
        dictionary = yaml.safe_load(stream)

    images = get_all_directories()

    gdf = read_geojson()

    df = create_dataframe()

    total_pixel = 0
    total_pixel_set = False
    
    for raster_image_path in images:
        date = np.datetime64(os.path.basename(os.path.dirname(raster_image_path)))
        plots_directory = os.path.dirname(raster_image_path) + dictionary['files']['plots_dir_name']
        
        if not os.path.exists(plots_directory):
            os.makedirs(plots_directory)

        output_str = ''
    
        with rasterio.open(raster_image_path) as src:
            # Check if the CRS match
            assert str(src.crs) == gdf.crs

            # Crop images of all plots, distinguished by id
            for id in gdf['id']:
                crop_plot(gdf, id, src, plots_directory)

                image_rotated = dictionary['image_correction']['image_rotated']

                if not image_rotated:
                    image_name = plots_directory + f"plot_{id}.tif"
                else:
                    rotate_plot(plots_directory, id)
                    image_name = plots_directory + f"plot_{id}_rotated_cropped.tif"
                    
                if not total_pixel_set:
                    im = Image.open(image_name)
                    size = im.size
                    total_pixel = size[0] * size[1]
                    total_pixel_set = True

                result = mask_image(image_name)
                percent = get_pixel_percent(result, total_pixel)

                string = f"""
                ID:               {id}
                date:             {date}
                total pixels:     {total_pixel}
                pixel-percentage: {percent}
                """
                print(string)

                df.loc[len(df.index)] = [date, id, percent]

        
    write_to_file(df)


if __name__ == "__main__":
    main()
