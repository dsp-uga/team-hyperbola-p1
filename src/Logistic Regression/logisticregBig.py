from pyspark.sql import SparkSession
from pyspark import SparkContext, SparkConf
from pyspark.sql import SQLContext
from pyspark.sql import functions as fn
from pyspark.ml.classification import NaiveBayes, LogisticRegression
from pyspark.ml.feature import HashingTF, RegexTokenizer,IDF,NGram
from pyspark.ml.evaluation import MulticlassClassificationEvaluator
from pyspark.sql.types import *
from pyspark.ml import Pipeline
import requests
import re


spark = SparkSession(sc)

def dataclean(dataframe):
	byte_path = 'https://storage.googleapis.com/uga-dsp/project1/data/bytes/'
	remove_id = fn.udf(lambda x : re.sub('\w{3,20}','',x))
	text_lower = fn.udf(lambda x: x.lower())
	get_byte_file = fn.udf(lambda x: requests.get(byte_path+x+'.bytes').text)
	data_df = dataframe.withColumnRenamed('value','Filename')\
		.repartition(96)\
		.withColumn('text_full',get_byte_file('Filename'))\
		.withColumn('text without line id', remove_id('text_full'))\
		.withColumn('text', text_lower('text without line id'))
	return data_df


def addlabel(X_datadf,y_datadf):
	X_data_id = X_datadf.withColumn('id',fn.monotonically_increasing_id())
	y_data_id = y_datadf.withColumn('id',fn.monotonically_increasing_id()).withColumnRenamed('value','label')
	df_joined = X_data_id.join(y_data_id,X_data_id.id == y_data_id.id,"left").drop('id')
	return  df_joined


def LR_Model(train_dataframe,test_dataframe):
	train_dataframe = train_dataframe.repartition(96).withColumn('label',train_dataframe['label'].cast(IntegerType()))
	regexTokenizer = RegexTokenizer(inputCol="text", outputCol="words", pattern="\\W|\b(00|CC)\b")
	ngram = NGram(n=3,inputCol="words", outputCol="ngrams")
	hashingTF = HashingTF(inputCol="ngrams", outputCol="TF")
	idf = IDF(inputCol="TF", outputCol="features")
	lr = LogisticRegression(maxIter=20, regParam=0.001)
	pipeline = Pipeline(stages=[regexTokenizer, ngram, hashingTF, idf, lr])
	model = pipeline.fit(train_dataframe)
	predictions_df = model.transform(test_dataframe)
	return predictions_df.select('prediction','given_order')



def get_accuracy(dataframe):
	dataframe = dataframe.withColumn('label',dataframe['label'].cast(DoubleType()))
	#dataframe = dataframe.withColumn('added_label',dataframe['added_label'].cast(DoubleType()))
	evaluator = MulticlassClassificationEvaluator(labelCol="label", predictionCol="prediction", metricName="accuracy")
	accuracy = evaluator.evaluate(dataframe)
	print("Test set accuracy = " + str(accuracy))
	
https://github.com/dsp-uga/team-hyperbola-p1.git
def save_predictions_to_file(dataframe, filename):
	dataframe = dataframe.sort('given_order')
	dataframe = dataframe.withColumn('pred_label',dataframe['prediction'].cast(IntegerType()))
	dataframe.select('pred_label').coalesce(1).write.mode('overwrite').csv('gs://team_hyperbola_p1/big_data/'+filename+'.csv')
	print('Saved!!')


X_train_df = spark.read.text('gs://uga-dsp/project1/files/X_train.txt')
y_train_df = spark.read.text('gs://uga-dsp/project1/files/y_train.txt')
X_test_df = spark.read.text('gs://uga-dsp/project1/files/X_test.txt')
X_test_df =  X_test_df.withColumn('given_order',fn.monotonically_increasing_id())
X_train_df =  X_train_df.withColumn('given_order',fn.monotonically_increasing_id())


train_data =  addlabel(X_train_df,y_train_df).repartition(96)
train_data_clean = dataclean(train_data).repartition(96)
#test_data = addlabel(X_test_df,y_test_df).repartition(96)
test_data_clean = dataclean(X_test_df).repartition(96)


predictions = LR_Model(train_data_clean, test_data_clean)
save_predictions_to_file(predictions, 'LR1.txt')



