variable "project_name" { type = string }
variable "environment_name" { type = string }
variable "container_image" { type = string }
variable "container_image_tag" { type = string }
variable "replica_count_api" { type = number }
variable "replica_count_worker" { type = number }
variable "enable_local_model_runtime" { type = bool }
