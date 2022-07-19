#!/usr/bin/env python3
"""
Author : Nimet Beyza Bozdag
Date   : 2022-07-18
Purpose: Analyze the canopy cover percentage of plots over a field.
"""

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

    parser.add_argument('-v',
                        '--verbose',
                        help='Put verbose mode ON',
                        action='store_true')


    return parser.parse_args()


def get_all_directories():
    """
    Returns the list of scan-date directories.
    """
    dates_dir = dictionary['files']['dates_dir']
    return glob.glob(os.path.join(dates_dir, "*", "*.tif"), recursive=True)


def read_geojson():
    """
    Reads the geojson and returns the geopandas dataframe with CRS set to the common ESPG value.
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
    Creates and returns dataframe to be outputted into the CSV file.
    """
    return pd.DataFrame(columns=["Date", "ID", "Percentage"])


def crop_plot(gdf, id, src, plots_directory):
    """
    Finds geospacial information about the plot to be cropped from the larger field tif and
    saves the cropped image as a tif file.

    Input:
        - gdf: geopandas dataframe with geojson information of the plots
        - id: int of the plot number
        - src: raster image file
        - plots_directory: string for directory to save the cropped plot image

    Output:
        - cropped plot saved in tif format
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
    Rotates the plot image if the image is not straight. 

    Input:
        - plots_directory: string for directory to save the cropped plot image
        - id: int of the plot number

    Output:
        - rotated plot image saved both as tif and png
    """

    # read image file 
    img, path, filename = pcv.readimage(filename = plots_directory + f"plot_{id}.tif")

    # row, and col count how many rows and columns there are from 
    # top left corner until a colored (non-black) pixel is found, respectively. 
    row, col, offset = 0, 0, 1

    # create numpy array with rgb for black (0, 0, 0) to use for comparisons
    black = np.zeros((1,3), dtype = np.int8)

    for i in range(len(img[0])):
        if not np.array_equal(img[offset][i], black[0]):
            col = i
            break

    for j in range(len(img)):
        if not np.array_equal(img[j][offset], black[0]):
            row = j
            break

    # calculate the angle by which the image is rotated
    ratio = (col - offset)/(row - offset)
    angle = np.arctan(ratio) * 180 / np.pi

    input_image = Image.open(plots_directory + f"plot_{id}.tif")

    # rotate image
    output = input_image.rotate(angle)

    # save image
    im2 = output.crop(output.getbbox())
    im2.save(plots_directory + f"plot_{id}_rotated_cropped.tif")
    im2.save(plots_directory + f"plot_{id}_rotated_cropped.png")


def mask_image(image_name):
    """
    Masks out the bakground of the image leaving only th green pixels that fall in the 
    range given by lower and upper. 

    Input:
        - image_name: string with file to be opened and masked
    
    Return value:
        - image (numpy array) with white background 
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
    Returns the percentage of non-white pixels to all pixels.

    Input:
        - image: numpy array of all pixels of an image
        - total_pixel: int for total pixels (set by the first processed plot's size)

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
    Writes data frame to csv file.

    Input:
        - df: dataframe to be written to output file

    Output:
        - csv file 
    """
    dates_dir = dictionary['files']['dates_dir']
    csv_name = dictionary['files']['csv_name']
    df.to_csv(dates_dir + "/" + csv_name)


def main():

    args = get_args()

    # get yaml dictionary from the command line argument
    with open(args.yaml, 'r') as stream:
        global dictionary
        dictionary = yaml.safe_load(stream)

    images = get_all_directories()

    gdf = read_geojson()

    df = create_dataframe()

    total_pixel = 0
    total_pixel_set = False
    
    # loop over all the scan-dates
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

                if args.verbose:
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
