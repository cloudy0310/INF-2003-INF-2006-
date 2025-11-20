import sys
from awsglue.context import GlueContext
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.window import Window

args = getResolvedOptions(sys.argv, ['RAW_PATH', 'OUTPUT_PATH'])
RAW_PATH = args['RAW_PATH']
OUTPUT_PATH = args['OUTPUT_PATH']

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session

spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")
spark.conf.set("spark.sql.shuffle.partitions", "200")

df = spark.read.parquet(RAW_PATH)

df = (
    df.withColumn("Date", F.col("Date").cast("timestamp"))
      .withColumn("Open", F.col("Open").cast("double"))
      .withColumn("High", F.col("High").cast("double"))
      .withColumn("Low", F.col("Low").cast("double"))
      .withColumn("Close", F.col("Close").cast("double"))
      .withColumn("Volume", F.col("Volume").cast("bigint"))
)

w = Window.partitionBy("Ticker").orderBy("Date")
w20 = w.rowsBetween(-19, 0)
w14 = w.rowsBetween(-13, 0)
w12 = w.rowsBetween(-11, 0)
w26 = w.rowsBetween(-25, 0)
wsig = w.rowsBetween(-8, 0)

# Bollinger Bands (20)
df = df.withColumn("bb_sma_20", F.avg("Close").over(w20))
df = df.withColumn("bb_std_20", F.stddev("Close").over(w20))
df = df.withColumn("bb_upper_20", F.col("bb_sma_20") + 2 * F.col("bb_std_20"))
df = df.withColumn("bb_lower_20", F.col("bb_sma_20") - 2 * F.col("bb_std_20"))

# RSI (14)
delta = F.col("Close") - F.lag("Close", 1).over(w)
gain = F.when(delta > 0, delta).otherwise(0.0)
loss = F.when(delta < 0, -delta).otherwise(0.0)
df = df.withColumn("avg_gain", F.avg(gain).over(w14))
df = df.withColumn("avg_loss", F.avg(loss).over(w14))
df = df.withColumn("rs", F.col("avg_gain") / F.col("avg_loss"))
df = df.withColumn("rsi_14", 100 - (100 / (1 + F.col("rs"))))

# MACD (12 EMA, 26 EMA, 9 Signal)
df = df.withColumn("ema12", F.avg("Close").over(w12))
df = df.withColumn("ema26", F.avg("Close").over(w26))
df = df.withColumn("macd", F.col("ema12") - F.col("ema26"))
df = df.withColumn("macd_signal", F.avg("macd").over(wsig))
df = df.withColumn("macd_hist", F.col("macd") - F.col("macd_signal"))

# Buy/Sell Signals
df = df.withColumn("buy_signal",
    (F.col("macd") < F.col("macd_signal")) &
    (F.col("macd") < 0) &
    (F.col("rsi_14") < 30) &
    (F.col("Close") <= F.col("bb_lower_20"))
)

df = df.withColumn("sell_signal",
    (F.col("macd") > F.col("macd_signal")) &
    (F.col("macd") > 0) &
    (F.col("rsi_14") > 70) &
    (F.col("Close") >= F.col("bb_upper_20"))
)

df = df.withColumn("year", F.year("Date"))
df = df.withColumn("month", F.month("Date"))

(
    df.write
      .mode("overwrite")
      .partitionBy("Ticker", "year", "month")
      .parquet(OUTPUT_PATH)
)
