# VPC (default to keep things simple)
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# Security group for EC2 + RDS
resource "aws_security_group" "app_sg" {
  name        = "school-proto-sg"
  description = "Allow HTTP, SSH, Postgres"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "Postgres"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [data.aws_vpc.default.cidr_block]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# EC2 for Streamlit
resource "aws_instance" "streamlit" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.ec2_instance_type
  vpc_security_group_ids = [aws_security_group.app_sg.id]
  subnet_id              = tolist(data.aws_subnets.default.ids)[0]

  user_data = <<-EOF
              #!/bin/bash
              apt-get update -y
              apt-get install -y python3-pip
              pip3 install streamlit psycopg2-binary boto3
              # Example: run a hello app on startup
              echo "import streamlit as st; st.title('Hello from Streamlit on EC2')" > /home/ubuntu/app.py
              nohup streamlit run /home/ubuntu/app.py --server.port=80 --server.headless=true &
              EOF

  tags = {
    Name = "StreamlitFrontend"
  }
}

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-focal-20.04-amd64-server-*"]
  }
}

# RDS instance
resource "aws_db_instance" "schooldb" {
  allocated_storage    = 20
  engine               = "postgres"
  engine_version       = "13"
  instance_class       = "db.t3.micro"
  db_name              = var.db_name
  username             = var.db_username
  password             = var.db_password
  skip_final_snapshot  = true
  publicly_accessible  = true
  vpc_security_group_ids = [aws_security_group.app_sg.id]
}

# Lambda + API Gateway for DB read
resource "aws_iam_role" "lambda_exec" {
  name = "school-lambda-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "read_api" {
  function_name    = "read-api"
  filename         = var.lambda_filename
  handler          = "handler.lambda_handler"
  runtime          = "python3.9"
  source_code_hash = filebase64sha256(var.lambda_filename)
  role             = aws_iam_role.lambda_exec.arn

  environment {
    variables = {
      DB_HOST     = aws_db_instance.schooldb.address
      DB_NAME     = var.db_name
      DB_USER     = var.db_username
      DB_PASSWORD = var.db_password
    }
  }
}

resource "aws_apigatewayv2_api" "http_api" {
  name          = "school-http-api"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "lambda_integration" {
  api_id                 = aws_apigatewayv2_api.http_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.read_api.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "default_route" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "ANY /read"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_integration.id}"
}

resource "aws_lambda_permission" "apigw_permission" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.read_api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}

resource "aws_apigatewayv2_stage" "default_stage" {
  api_id      = aws_apigatewayv2_api.http_api.id
  name        = "$default"
  auto_deploy = true
}

