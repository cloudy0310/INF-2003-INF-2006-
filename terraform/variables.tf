variable "aws_region" {
  description = "AWS region to deploy to"
  type        = string
  default     = "ap-southeast-1"
}

variable "ec2_instance_type" {
  description = "EC2 instance type for Streamlit frontend"
  type        = string
  default     = "t3.micro"
}

variable "db_name" {
  description = "Name of RDS database"
  type        = string
  default     = "schooldb"
}

variable "db_username" {
  description = "Master username for RDS"
  type        = string
  default     = "postgres"
}

variable "db_password" {
  description = "Master password for RDS"
  type        = string
  sensitive   = true
}

variable "lambda_filename" {
  description = "Path to Lambda deployment package zip"
  type        = string
  default     = "lambda/read_api.zip"
}
