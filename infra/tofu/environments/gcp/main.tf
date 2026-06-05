module "network" { source = "../../modules/network" environment_name = "gcp" project_name = "llmproxy" region = "us-central1" vpc_cidr = "10.20.0.0/16" }
module "secrets" { source = "../../modules/secrets" environment_name = "gcp" project_name = "llmproxy" }
module "storage" { source = "../../modules/storage" artifact_bucket_name = "llmproxy-gcp-artifacts" }
module "postgres" { source = "../../modules/postgres" environment_name = "gcp" project_name = "llmproxy" db_instance_class = "db-custom-2-7680" }
module "redis" { source = "../../modules/redis" environment_name = "gcp" project_name = "llmproxy" redis_instance_class = "standard-small" }
module "kubernetes_cluster" { source = "../../modules/kubernetes_cluster" environment_name = "gcp" project_name = "llmproxy" region = "us-central1" }
module "observability" { source = "../../modules/observability" environment_name = "gcp" project_name = "llmproxy" }
module "llmproxy_app" {
  source = "../../modules/llmproxy_app"
  project_name = "llmproxy"
  environment_name = "gcp"
  container_image = "llmproxy"
  container_image_tag = "latest"
  replica_count_api = 2
  replica_count_worker = 2
  enable_local_model_runtime = false
}
