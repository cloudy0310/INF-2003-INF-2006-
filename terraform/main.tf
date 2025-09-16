locals {
  name       = var.project
  app_fqdn   = "${var.app_subdomain}.${var.domain_name}"
  admin_fqdn = "${var.admin_subdomain}.${var.domain_name}"
}

data "aws_availability_zones" "azs" { state = "available" }
data "aws_caller_identity" "this" {}

locals {
  azs           = slice(data.aws_availability_zones.azs.names, 0, var.az_count)
  public_cidrs  = [for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 4, i)]
  private_cidrs = [for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 4, i + 8)]
}

# ---------------- VPC ----------------
resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags = { Name = "${local.name}-vpc" }
}

resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.this.id
  tags = { Name = "${local.name}-igw" }
}

resource "aws_subnet" "public" {
  for_each = toset(local.azs)
  vpc_id                  = aws_vpc.this.id
  cidr_block              = local.public_cidrs[index(local.azs, each.key)]
  availability_zone       = each.key
  map_public_ip_on_launch = true
  tags = { Name = "${local.name}-public-${each.key}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
  tags = { Name = "${local.name}-pub-rt" }
}

resource "aws_route" "public_inet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.igw.id
}

resource "aws_route_table_association" "pub_assoc" {
  for_each       = aws_subnet.public
  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}

# NAT for private
resource "aws_eip" "nat" { domain = "vpc"  tags = { Name = "${local.name}-nat-eip" } }

resource "aws_nat_gateway" "nat" {
  allocation_id = aws_eip.nat.id
  subnet_id     = values(aws_subnet.public)[0].id
  depends_on    = [aws_internet_gateway.igw]
  tags = { Name = "${local.name}-nat" }
}

resource "aws_subnet" "private" {
  for_each = toset(local.azs)
  vpc_id                  = aws_vpc.this.id
  cidr_block              = local.private_cidrs[index(local.azs, each.key)]
  availability_zone       = each.key
  map_public_ip_on_launch = false
  tags = { Name = "${local.name}-private-${each.key}" }
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.this.id
  tags = { Name = "${local.name}-priv-rt" }
}

resource "aws_route" "private_nat" {
  route_table_id         = aws_route_table.private.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.nat.id
}

resource "aws_route_table_association" "priv_assoc" {
  for_each       = aws_subnet.private
  subnet_id      = each.value.id
  route_table_id = aws_route_table.private.id
}

# ---------------- Security Groups ----------------
resource "aws_security_group" "alb_sg" {
  name        = "${local.name}-alb-sg"
  description = "ALB ingress 80/443"
  vpc_id      = aws_vpc.this.id

  ingress { from_port = 80  to_port = 80  protocol = "tcp" cidr_blocks = ["0.0.0.0/0"] ipv6_cidr_blocks = ["::/0"] }
  ingress { from_port = 443 to_port = 443 protocol = "tcp" cidr_blocks = ["0.0.0.0/0"] ipv6_cidr_blocks = ["::/0"] }
  egress  { from_port = 0   to_port = 0   protocol = "-1"  cidr_blocks = ["0.0.0.0/0"] ipv6_cidr_blocks = ["::/0"] }
  tags = { Name = "${local.name}-alb-sg" }
}

resource "aws_security_group" "app_sg" {
  name        = "${local.name}-app-sg"
  description = "Allow ALB -> Streamlit 8501"
  vpc_id      = aws_vpc.this.id

  ingress {
    description     = "ALB to app on 8501"
    from_port       = 8501
    to_port         = 8501
    protocol        = "tcp"
    security_groups = [aws_security_group.alb_sg.id]
  }

  egress { from_port = 0 to_port = 0 protocol = "-1" cidr_blocks = ["0.0.0.0/0"] ipv6_cidr_blocks = ["::/0"] }
  tags = { Name = "${local.name}-app-sg" }
}

# ---------------- IAM for EC2 ----------------
resource "aws_iam_role" "ec2_role" {
  name = "${local.name}-ec2-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "ec2.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# EC2 → SSM params read + DDB access
resource "aws_iam_policy" "app_ssm_ddb" {
  name   = "${local.name}-ssm-ddb"
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect: "Allow",
        Action: ["ssm:GetParameter","ssm:GetParameters","ssm:GetParametersByPath"],
        Resource: "arn:aws:ssm:${var.region}:${data.aws_caller_identity.this.account_id}:parameter/${local.name}/*"
      },
      {
        Effect: "Allow",
        Action: [
          "dynamodb:BatchGetItem","dynamodb:GetItem","dynamodb:Query","dynamodb:Scan",
          "dynamodb:BatchWriteItem","dynamodb:PutItem","dynamodb:UpdateItem","dynamodb:DeleteItem"
        ],
        Resource: aws_dynamodb_table.prices.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "attach_app_ssm_ddb" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = aws_iam_policy.app_ssm_ddb.arn
}

resource "aws_iam_instance_profile" "ec2_profile" {
  name = "${local.name}-ec2-profile"
  role = aws_iam_role.ec2_role.name
}

# ---------------- AMI ----------------
data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]
  filter { name = "name" values = ["al2023-ami-*-x86_64"] }
}

# ---------------- RDS PostgreSQL ----------------
resource "aws_db_subnet_group" "db" {
  name       = "${local.name}-db-subnets"
  subnet_ids = [for s in aws_subnet.private : s.id]
  tags = { Name = "${local.name}-db-subnets" }
}

resource "aws_security_group" "rds_sg" {
  name        = "${local.name}-rds-sg"
  description = "Postgres from app SG"
  vpc_id      = aws_vpc.this.id

  ingress {
    description     = "App SG to Postgres"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.app_sg.id]
  }

  egress { from_port = 0 to_port = 0 protocol = "-1" cidr_blocks = ["0.0.0.0/0"] ipv6_cidr_blocks = ["::/0"] }
  tags = { Name = "${local.name}-rds-sg" }
}

resource "random_password" "db_password" {
  length  = 24
  special = true
}

resource "aws_db_instance" "postgres" {
  identifier              = "${local.name}-pg"
  engine                  = "postgres"
  engine_version          = var.db_engine_version
  instance_class          = var.db_instance_class
  allocated_storage       = var.db_allocated_storage
  db_name                 = var.db_name
  username                = var.db_username
  password                = random_password.db_password.result
  db_subnet_group_name    = aws_db_subnet_group.db.name
  vpc_security_group_ids  = [aws_security_group.rds_sg.id]
  multi_az                = false
  publicly_accessible     = false
  storage_encrypted       = true
  skip_final_snapshot     = true
  deletion_protection     = false
  apply_immediately       = true
  backup_retention_period = 1
  tags = { Name = "${local.name}-postgres" }
}

# ---------------- DynamoDB ----------------
resource "aws_dynamodb_table" "prices" {
  name         = var.ddb_prices_table
  billing_mode = "PAY_PER_REQUEST"

  hash_key  = "ticker"
  range_key = "date"

  attribute { name = "ticker"; type = "S" }
  attribute { name = "date";   type = "S" }

  tags = { Name = "${local.name}-prices" }
}

# ---------------- SSM parameters (DB + DDB + Cognito) ----------------
resource "aws_ssm_parameter" "db_host"      { name = "/${local.name}/db/host"      type = "String"       value = aws_db_instance.postgres.address }
resource "aws_ssm_parameter" "db_port"      { name = "/${local.name}/db/port"      type = "String"       value = tostring(aws_db_instance.postgres.port) }
resource "aws_ssm_parameter" "db_name"      { name = "/${local.name}/db/name"      type = "String"       value = var.db_name }
resource "aws_ssm_parameter" "db_user"      { name = "/${local.name}/db/user"      type = "String"       value = var.db_username }
resource "aws_ssm_parameter" "db_password"  { name = "/${local.name}/db/password"  type = "SecureString" value = random_password.db_password.result }
resource "aws_ssm_parameter" "ddb_prices"   { name = "/${local.name}/ddb/prices_table" type = "String"    value = aws_dynamodb_table.prices.name }

# ---------------- Cognito ----------------
resource "aws_cognito_user_pool" "pool" {
  name = "${local.name}-user-pool"
  schema {
    name                = "email"
    attribute_data_type = "String"
    required            = true
    mutable             = false
  }
  auto_verified_attributes = ["email"]
}

resource "aws_cognito_user_pool_domain" "domain" {
  domain       = var.cognito_domain_prefix
  user_pool_id = aws_cognito_user_pool.pool.id
}

resource "aws_cognito_user_pool_client" "user" {
  name                              = "${local.name}-user-client"
  user_pool_id                      = aws_cognito_user_pool.pool.id
  generate_secret                   = true
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows               = ["code"]
  allowed_oauth_scopes              = ["openid","email","profile"]
  callback_urls                     = ["https://${local.app_fqdn}/"]
  logout_urls                       = ["https://${local.app_fqdn}/"]
  supported_identity_providers      = ["COGNITO"]
}

resource "aws_cognito_user_pool_client" "admin" {
  name                              = "${local.name}-admin-client"
  user_pool_id                      = aws_cognito_user_pool.pool.id
  generate_secret                   = true
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows               = ["code"]
  allowed_oauth_scopes              = ["openid","email","profile"]
  callback_urls                     = ["https://${local.admin_fqdn}/"]
  logout_urls                       = ["https://${local.admin_fqdn}/"]
  supported_identity_providers      = ["COGNITO"]
}

resource "aws_cognito_user_group" "admin" {
  name         = "admin"
  user_pool_id = aws_cognito_user_pool.pool.id
  description  = "Administrators"
}

# Store Cognito details in SSM for the apps
resource "aws_ssm_parameter" "cog_domain"   { name = "/${local.name}/cognito/domain"      type = "String"       value = "${var.cognito_domain_prefix}.auth.${var.region}.amazoncognito.com" }
resource "aws_ssm_parameter" "cog_user_id"  { name = "/${local.name}/cognito/user_client_id" type = "String"    value = aws_cognito_user_pool_client.user.id }
resource "aws_ssm_parameter" "cog_user_sec" { name = "/${local.name}/cognito/user_client_secret" type = "SecureString" value = aws_cognito_user_pool_client.user.client_secret }
resource "aws_ssm_parameter" "cog_admin_id" { name = "/${local.name}/cognito/admin_client_id" type = "String"    value = aws_cognito_user_pool_client.admin.id }
resource "aws_ssm_parameter" "cog_admin_sec"{ name = "/${local.name}/cognito/admin_client_secret" type = "SecureString" value = aws_cognito_user_pool_client.admin.client_secret }
resource "aws_ssm_parameter" "cog_user_redirect"  { name = "/${local.name}/cognito/user_redirect_uri"  type = "String" value = "https://${local.app_fqdn}/" }
resource "aws_ssm_parameter" "cog_user_logout"    { name = "/${local.name}/cognito/user_logout_uri"    type = "String" value = "https://${local.app_fqdn}/" }
resource "aws_ssm_parameter" "cog_admin_redirect" { name = "/${local.name}/cognito/admin_redirect_uri" type = "String" value = "https://${local.admin_fqdn}/" }
resource "aws_ssm_parameter" "cog_admin_logout"   { name = "/${local.name}/cognito/admin_logout_uri"   type = "String" value = "https://${local.admin_fqdn}/" }

# ---------------- ACM (TLS) ----------------
resource "aws_acm_certificate" "cert" {
  domain_name               = var.domain_name
  subject_alternative_names = ["*.${var.domain_name}"]
  validation_method         = "DNS"
  lifecycle { create_before_destroy = true }
}

resource "aws_route53_record" "cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.cert.domain_validation_options :
    dvo.domain_name => {
      name  = dvo.resource_record_name
      type  = dvo.resource_record_type
      value = dvo.resource_record_value
    }
  }
  zone_id = var.zone_id
  name    = each.value.name
  type    = each.value.type
  ttl     = 60
  records = [each.value.value]
}

resource "aws_acm_certificate_validation" "cert" {
  certificate_arn         = aws_acm_certificate.cert.arn
  validation_record_fqdns = [for r in aws_route53_record.cert_validation : r.fqdn]
}

# ---------------- ALB + TG + Rules ----------------
resource "aws_lb" "app" {
  name               = "${local.name}-alb"
  load_balancer_type = "application"
  subnets            = [for s in aws_subnet.public : s.id]
  security_groups    = [aws_security_group.alb_sg.id]
  idle_timeout       = 120
  tags = { Name = "${local.name}-alb" }
}

resource "aws_lb_target_group" "user" {
  name     = "${local.name}-tg-user"
  port     = 8501
  protocol = "HTTP"
  vpc_id   = aws_vpc.this.id
  health_check { path = "/" matcher = "200,302" interval = 15 timeout = 5 healthy_threshold = 3 unhealthy_threshold = 3 }
}

resource "aws_lb_target_group" "admin" {
  name     = "${local.name}-tg-admin"
  port     = 8501
  protocol = "HTTP"
  vpc_id   = aws_vpc.this.id
  health_check { path = "/" matcher = "200,302" interval = 15 timeout = 5 }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.app.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type = "redirect"
    redirect { port = "443" protocol = "HTTPS" status_code = "HTTP_301" }
  }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.app.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-2016-08"
  certificate_arn   = aws_acm_certificate_validation.cert.certificate_arn
  default_action { type = "forward" target_group_arn = aws_lb_target_group.user.arn }
}

resource "aws_lb_listener_rule" "host_admin" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 10
  action { type = "forward" target_group_arn = aws_lb_target_group.admin.arn }
  condition { host_header { values = [local.admin_fqdn] } }
}

# ---------------- Route53 aliases ----------------
resource "aws_route53_record" "app" {
  zone_id = var.zone_id
  name    = local.app_fqdn
  type    = "A"
  alias { name = aws_lb.app.dns_name zone_id = aws_lb.app.zone_id evaluate_target_health = true }
}

resource "aws_route53_record" "admin" {
  zone_id = var.zone_id
  name    = local.admin_fqdn
  type    = "A"
  alias { name = aws_lb.app.dns_name zone_id = aws_lb.app.zone_id evaluate_target_health = true }
}

# ---------------- EC2s (private) ----------------
# User EC2
resource "aws_instance" "user" {
  ami                         = data.aws_ami.al2023.id
  instance_type               = var.instance_type_user
  subnet_id                   = values(aws_subnet.private)[0].id
  vpc_security_group_ids      = [aws_security_group.app_sg.id]
  iam_instance_profile        = aws_iam_instance_profile.ec2_profile.name
  key_name                    = var.key_name
  associate_public_ip_address = false

  user_data = <<-EOF
    #!/bin/bash
    set -eux
    dnf update -y
    dnf install -y git python3-pip awscli
    pip3 install --upgrade pip
    pip3 install streamlit python-dotenv supabase streamlit-option-menu plotly requests boto3 PyJWT

    APP_ROOT="/opt/app"
    REGION="${var.region}"
    PROJECT="${local.name}"

    mkdir -p "${APP_ROOT}"
    cd /opt
    if [ ! -d "${APP_ROOT}/.git" ]; then
      git clone --branch ${var.repo_branch} ${var.repo_url} app
    else
      cd ${APP_ROOT} && git fetch && git checkout ${var.repo_branch} && git pull
    fi

    # Fetch SSM params
    DB_HOST=$(aws ssm get-parameter --name "/${local.name}/db/host" --query Parameter.Value --output text --region ${var.region})
    DB_PORT=$(aws ssm get-parameter --name "/${local.name}/db/port" --query Parameter.Value --output text --region ${var.region})
    DB_NAME=$(aws ssm get-parameter --name "/${local.name}/db/name" --query Parameter.Value --output text --region ${var.region})
    DB_USER=$(aws ssm get-parameter --name "/${local.name}/db/user" --query Parameter.Value --output text --region ${var.region})
    DB_PASSWORD=$(aws ssm get-parameter --with-decryption --name "/${local.name}/db/password" --query Parameter.Value --output text --region ${var.region})
    DDB_PRICES_TABLE=$(aws ssm get-parameter --name "/${local.name}/ddb/prices_table" --query Parameter.Value --output text --region ${var.region})

    COG_DOMAIN=$(aws ssm get-parameter --name "/${local.name}/cognito/domain" --query Parameter.Value --output text --region ${var.region})
    COG_CLIENT_ID=$(aws ssm get-parameter --name "/${local.name}/cognito/user_client_id" --query Parameter.Value --output text --region ${var.region})
    COG_CLIENT_SECRET=$(aws ssm get-parameter --with-decryption --name "/${local.name}/cognito/user_client_secret" --query Parameter.Value --output text --region ${var.region})
    COG_REDIRECT=$(aws ssm get-parameter --name "/${local.name}/cognito/user_redirect_uri" --query Parameter.Value --output text --region ${var.region})
    COG_LOGOUT=$(aws ssm get-parameter --name "/${local.name}/cognito/user_logout_uri" --query Parameter.Value --output text --region ${var.region})

    # Write .env for user_portal
    cat >${APP_ROOT}/user_portal/.env <<ENV
DB_HOST=${DB_HOST}
DB_PORT=${DB_PORT}
DB_NAME=${DB_NAME}
DB_USER=${DB_USER}
DB_PASSWORD=${DB_PASSWORD}
DDB_PRICES_TABLE=${DDB_PRICES_TABLE}
COGNITO_DOMAIN=${COG_DOMAIN}
COGNITO_CLIENT_ID=${COG_CLIENT_ID}
COGNITO_CLIENT_SECRET=${COG_CLIENT_SECRET}
COGNITO_REDIRECT_URI=${COG_REDIRECT}
COGNITO_LOGOUT_URI=${COG_LOGOUT}
ENV

    # systemd
    cat >/etc/systemd/system/user-portal.service <<'UNIT'
    [Unit]
    Description=User Portal (Streamlit)
    After=network.target

    [Service]
    WorkingDirectory=/opt/app/user_portal
    ExecStart=/usr/bin/streamlit run app.py --server.port 8501 --server.address 0.0.0.0
    Restart=always
    Environment="PYTHONUNBUFFERED=1"

    [Install]
    WantedBy=multi-user.target
    UNIT

    systemctl daemon-reload
    systemctl enable --now user-portal
  EOF

  tags = { Name = "${local.name}-user-ec2" }
}

# Admin EC2
resource "aws_instance" "admin" {
  ami                         = data.aws_ami.al2023.id
  instance_type               = var.instance_type_admin
  subnet_id                   = values(aws_subnet.private)[1].id
  vpc_security_group_ids      = [aws_security_group.app_sg.id]
  iam_instance_profile        = aws_iam_instance_profile.ec2_profile.name
  key_name                    = var.key_name
  associate_public_ip_address = false

  user_data = <<-EOF
    #!/bin/bash
    set -eux
    dnf update -y
    dnf install -y git python3-pip awscli
    pip3 install --upgrade pip
    pip3 install streamlit python-dotenv supabase streamlit-option-menu plotly requests boto3 PyJWT

    APP_ROOT="/opt/app"
    REGION="${var.region}"
    PROJECT="${local.name}"

    mkdir -p "${APP_ROOT}"
    cd /opt
    if [ ! -d "${APP_ROOT}/.git" ]; then
      git clone --branch ${var.repo_branch} ${var.repo_url} app
    else
      cd ${APP_ROOT} && git fetch && git checkout ${var.repo_branch} && git pull
    fi

    # Fetch SSM params
    DB_HOST=$(aws ssm get-parameter --name "/${local.name}/db/host" --query Parameter.Value --output text --region ${var.region})
    DB_PORT=$(aws ssm get-parameter --name "/${local.name}/db/port" --query Parameter.Value --output text --region ${var.region})
    DB_NAME=$(aws ssm get-parameter --name "/${local.name}/db/name" --query Parameter.Value --output text --region ${var.region})
    DB_USER=$(aws ssm get-parameter --name "/${local.name}/db/user" --query Parameter.Value --output text --region ${var.region})
    DB_PASSWORD=$(aws ssm get-parameter --with-decryption --name "/${local.name}/db/password" --query Parameter.Value --output text --region ${var.region})
    DDB_PRICES_TABLE=$(aws ssm get-parameter --name "/${local.name}/ddb/prices_table" --query Parameter.Value --output text --region ${var.region})

    COG_DOMAIN=$(aws ssm get-parameter --name "/${local.name}/cognito/domain" --query Parameter.Value --output text --region ${var.region})
    COG_CLIENT_ID=$(aws ssm get-parameter --name "/${local.name}/cognito/admin_client_id" --query Parameter.Value --output text --region ${var.region})
    COG_CLIENT_SECRET=$(aws ssm get-parameter --with-decryption --name "/${local.name}/cognito/admin_client_secret" --query Parameter.Value --output text --region ${var.region})
    COG_REDIRECT=$(aws ssm get-parameter --name "/${local.name}/cognito/admin_redirect_uri" --query Parameter.Value --output text --region ${var.region})
    COG_LOGOUT=$(aws ssm get-parameter --name "/${local.name}/cognito/admin_logout_uri" --query Parameter.Value --output text --region ${var.region})

    # Write .env for admin_portal
    cat >${APP_ROOT}/admin_portal/.env <<ENV
DB_HOST=${DB_HOST}
DB_PORT=${DB_PORT}
DB_NAME=${DB_NAME}
DB_USER=${DB_USER}
DB_PASSWORD=${DB_PASSWORD}
DDB_PRICES_TABLE=${DDB_PRICES_TABLE}
COGNITO_DOMAIN=${COG_DOMAIN}
COGNITO_CLIENT_ID=${COG_CLIENT_ID}
COGNITO_CLIENT_SECRET=${COG_CLIENT_SECRET}
COGNITO_REDIRECT_URI=${COG_REDIRECT}
COGNITO_LOGOUT_URI=${COG_LOGOUT}
ENV

    # systemd
    cat >/etc/systemd/system/admin-portal.service <<'UNIT'
    [Unit]
    Description=Admin Portal (Streamlit)
    After=network.target

    [Service]
    WorkingDirectory=/opt/app/admin_portal
    ExecStart=/usr/bin/streamlit run app.py --server.port 8501 --server.address 0.0.0.0
    Restart=always
    Environment="PYTHONUNBUFFERED=1"

    [Install]
    WantedBy=multi-user.target
    UNIT

    systemctl daemon-reload
    systemctl enable --now admin-portal
  EOF

  tags = { Name = "${local.name}-admin-ec2" }
}

# Target groups ← instances
resource "aws_lb_target_group_attachment" "att_user" {
  target_group_arn = aws_lb_target_group.user.arn
  target_id        = aws_instance.user.id
  port             = 8501
}

resource "aws_lb_target_group_attachment" "att_admin" {
  target_group_arn = aws_lb_target_group.admin.arn
  target_id        = aws_instance.admin.id
  port             = 8501
}
