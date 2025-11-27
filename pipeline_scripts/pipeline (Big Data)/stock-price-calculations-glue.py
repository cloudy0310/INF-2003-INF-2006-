import sys
from awsglue.context import GlueContext
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
import pyspark.sql.functions as F
from pyspark.sql.window import Window

args = getResolvedOptions(sys.argv, ["S3_INPUT", "S3_OUTPUT"])

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session

S3_INPUT = args["S3_INPUT"] 
S3_OUTPUT = args["S3_OUTPUT"] 

df = spark.read.parquet(S3_INPUT)

# Ensure types
df = df.withColumn("Date", F.col("Date").cast("timestamp"))
df = df.withColumn("Close", F.col("Close").cast("double"))

window_14 = Window.partitionBy("ticker").orderBy("Date").rowsBetween(-13, 0)
window_20 = Window.partitionBy("ticker").orderBy("Date").rowsBetween(-19, 0)
window_50 = Window.partitionBy("ticker").orderBy("Date").rowsBetween(-49, 0)

# Technical Indicators

# SMA
df = df.withColumn("SMA20", F.avg("Close").over(window_20))
df = df.withColumn("SMA50", F.avg("Close").over(window_50))

# EMA
df = df.withColumn("EMA12", F.avg("Close").over(Window.partitionBy("ticker").orderBy("Date").rowsBetween(-11, 0)))
df = df.withColumn("EMA26", F.avg("Close").over(Window.partitionBy("ticker").orderBy("Date").rowsBetween(-25, 0)))

# MACD
df = df.withColumn("MACD", F.col("EMA12") - F.col("EMA26"))
signal_window = Window.partitionBy("ticker").orderBy("Date").rowsBetween(-8, 0)
df = df.withColumn("Signal", F.avg("MACD").over(signal_window))

df = df.withColumn("Histogram", F.col("MACD") - F.col("Signal"))

# RSI
change = F.col("Close") - F.lag("Close", 1).over(Window.partitionBy("ticker").orderBy("Date"))
gain = F.when(change > 0, change).otherwise(0)
loss = F.when(change < 0, -change).otherwise(0)

df = df.withColumn("Gain", gain)
df = df.withColumn("Loss", loss)

df = df.withColumn("AvgGain", F.avg("Gain").over(window_14))
df = df.withColumn("AvgLoss", F.avg("Loss").over(window_14))
df = df.withColumn("RS", F.col("AvgGain") / F.col("AvgLoss"))
df = df.withColumn("RSI", 100 - (100 / (1 + F.col("RS"))))

# Boll
df = df.withColumn("StdDev20", F.stddev("Close").over(window_20))
df = df.withColumn("UpperBand", F.col("SMA20") + 2 * F.col("StdDev20"))
df = df.withColumn("LowerBand", F.col("SMA20") - 2 * F.col("StdDev20"))


# Trading Signals
df = df.withColumn(
    "BuySignal",
    F.when((F.col("MACD") > F.col("Signal")) & (F.lag("MACD", 1).over(Window.partitionBy("ticker").orderBy("Date")) <= F.lag("Signal", 1).over(Window.partitionBy("ticker").orderBy("Date"))), 1).otherwise(0)
)

df = df.withColumn(
    "SellSignal",
    F.when((F.col("MACD") < F.col("Signal")) & (F.lag("MACD", 1).over(Window.partitionBy("ticker").orderBy("Date")) >= F.lag("Signal", 1).over(Window.partitionBy("ticker").orderBy("Date"))), 1).otherwise(0)
)

# Write
df.write.mode("overwrite").parquet(S3_OUTPUT)

