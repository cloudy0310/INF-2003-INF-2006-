variable "project"         { type = string }
variable "region"          { type = string }

# DNS (you must already have a hosted zone in Route 53)
variable "domain_name"     { type = string } # e.g. example.com
variable "zone_id"         { type = string } # hosted zone ID for domain_name

variable "app_subdomain"   { type = string  default = "app" }
variable "admin_subdomain" { type = string  default = "admin" }

# VPC/EC2
variable "vpc_cidr"        { type = string  default = "10.20.0.0/16" }
variable "az_count"        { type = number  default = 2 }
variable "instance_type_user"  { type = string default = "t3.small" }
variable "instance_type_admin" { type = string default = "t3.small" }
variable "key_name"            { type = string default = null }    # optional SSH key

# Your code repo
variable "repo_url"        { type = string }                       # e.g. https://github.com/you/yourrepo.git
variable "repo_branch"     { type = string default = "main" }

# Cognito
variable "cognito_domain_prefix" { type = string } # must be globally unique in the region

# Database/DynamoDB
variable "db_name"              { type = string  default = "appdb" }
variable "db_username"          { type = string  default = "appuser" }
variable "db_instance_class"    { type = string  default = "db.t4g.micro" }
variable "db_allocated_storage" { type = number  default = 20 }
variable "db_engine_version"    { type = string  default = "15.4" } # PostgreSQL
variable "ddb_prices_table"     { type = string  default = "stock_prices" }
