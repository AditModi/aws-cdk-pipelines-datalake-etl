# Copyright 2020 Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
import boto3
from boto3.dynamodb.conditions import Key
from pyspark.sql import HiveContext
from awsglue.dynamicframe import DynamicFrame

from datetime import datetime
import botocore


## @params: [JOB_NAME]
args = getResolvedOptions(sys.argv, ['JOB_NAME','dynamodb_tablename','target_databasename','target_tablename','target_bucketname','source_bucketname','source_key','source_system_name','base_file_name','p_year','p_month','p_day','table_name'])


sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)
sqlContext=HiveContext(sc)


def table_exists(target_database,table_name):
    try:
        glue_client=boto3.client("glue")
        glue_client.get_table(DatabaseName=target_database,Name=table_name)
        return True
    except:
        return False

def create_database():
    response = None
    table_response = None
    
    glue_client = boto3.client('glue')
    database_name = args['target_databasename']
    
    try:
        # global response
        response = glue_client.get_database(
            Name=database_name
        )
        print(response)
    except botocore.exceptions.ClientError as error:
        if error.response['Error']['Code'] == 'EntityNotFoundException':
            print('The requested database: {0} was not found.'.format(database_name))
        else:
            print('Error Message: {}'.format(error.response['Error']['Message']))

    if response is None:
        print('I am going to create a database')
        response = glue_client.create_database(
            DatabaseInput={
                'Name': database_name
            }
        )
        print("create_database_response: ", response) 

def upsert_catalog_table(df,target_database,table_name,classification,storage_location):
    
    create_database()
    df_schema=df.dtypes
    schema=[]
    
    for s in df_schema:
        if (s[0] != 'year' and s[0] != 'month' and s[0] != 'day'):
            if s[1]=="decimal(10,0)":
                v={"Name": s[0], "Type": "int" }
            elif s[1]=="null":
                v={"Name": s[0], "Type": "string" }
            else:
                v={"Name": s[0], "Type": s[1] }
            schema.append(v)
        
    print(schema)
    #schema = transform.source_schema
    input_format = 'org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat'
    output_format = 'org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat'
    serde_info = {'Parameters': {'serialization.format': '1'},
                  'SerializationLibrary': 'org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe'}
    storeage_descriptor={'Columns': schema, 'InputFormat': input_format, 'OutputFormat': output_format, 'SerdeInfo': serde_info,
                'Location': storage_location}

    
    partition_key=[{'Name':'year', 'Type':'string'},{'Name':'month', 'Type':'string'},{'Name':'day', 'Type':'string'}]
    table_input = {'Name': table_name,
                  'StorageDescriptor' : storeage_descriptor, #self.get_storage_descriptor(target.output_format, schema, target.table_name),
                  'Parameters': {'classification': classification,
                                  'SourceType': "s3",
                                  'SourceTableName': table_name,
                                  'TableVersion': "0"},
                  'TableType': 'EXTERNAL_TABLE',
                  'PartitionKeys':partition_key
                  
                  }

    
    glue_client=boto3.client('glue')
    
    
    if not table_exists(target_database,table_name):
        print("[INFO] Target Table name: {} does not exist.".format(table_name))
        glue_client.create_table(DatabaseName=target_database, TableInput=table_input)
    else:
        print("[INFO] Trying to update: TargetTable: {}".format(table_name))
        glue_client.update_table(DatabaseName=target_database, TableInput=table_input) 
        
def add_partition(rec):

    partition_path= "{}/".format(args['p_year']) + "{}/".format(args['p_month']) + "{}/".format(args['p_day'])
    rec["year"]=args['p_year']
    rec["month"]=args['p_month']
    rec["day"]=args['p_day']
    print(partition_path)
    return rec
def main():
    
    year=datetime.today().year
    month=datetime.today().month
    day=datetime.today().day

    client=boto3.resource('dynamodb')
    print("after clinet connection")
    table=client.Table(args['dynamodb_tablename'])
    print("table connected")
    response = table.query(KeyConditionExpression=Key('load_name').eq("load_nyc_city_data"))
    
    print(response)
    
    items=[]
    for r in response['Items']:
        items.append(r)
    print(items)
    print("after for loop")
    for item in items:
        print("Target load Name: {}".format(item['load_name']))
        qry=item['transfer_logic']
        print(qry)
        df=sqlContext.sql(qry)
        

        
        partition_path= "year={}/".format(args['p_year']) + "month={}/".format(args['p_month']) + "day={}/".format(args['p_day'])
        target_s3_location="s3://" + args['target_bucketname']+"/datalake_blog/"
        storage_location=target_s3_location + args['table_name'] #+ "/" + partition_path
        upsert_catalog_table(df,args['target_databasename'],args['table_name'],'PARQUET',storage_location)
        
        spark.conf.set("spark.sql.sources.partitionOverwriteMode","dynamic")
        spark.conf.set("hive.exec.dynamic.partition", "true")
        spark.conf.set("hive.exec.dynamic.partition.mode", "nonstrict")
        
        
        df.write.partitionBy("year","month","day") \
            .format("parquet").save(storage_location, mode="overwrite")
    
        target_table_name = args['target_databasename']+ "." + args['table_name']
        spark.sql(f'ALTER TABLE {target_table_name} RECOVER PARTITIONS')
        

if __name__=="__main__":
    main()