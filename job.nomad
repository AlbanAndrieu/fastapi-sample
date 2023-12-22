# nomad job run -var env=uat -var team=uat job.nomad

variable "env" {
  type    = string
  default = "dev"

  validation {
    condition     = var.env == "dev" || var.env == "uat" || var.env == "prod"
    error_message = "The env value must be valid env uat or prod."
  }
}

variable "team" {
  type    = string
  default = "uat"

  validation {
    condition     = var.team == "ateam" || var.team == "bteam" || var.team == "uat" || var.team == "prod" || var.team == "dev"
    error_message = "The env value must be valid team ateam or bteam."
  }
}

variable "datacenters" {
  type        = list(string)
  description = "List of datacenters to deploy to."
  default     = ["gra"]
}

job "fastapi-sample" {
  datacenters = var.datacenters
  namespace   = "datascience"
  type        = "service"

  # Meta keys are also interpretable.
  meta {
    version  = "v0.0.1"
    region   = "${node.region}"
    dc       = "${node.datacenter}"
    scope   = "test"
    service  = "fastapi-sample-${var.env}"
    team     = "${var.team}"
    env     = "${var.env}"
  }

  group "fastapi-sample" {
    count = 1

    scaling {
      min     = 1
      max     = 4
      enabled = true

      policy {
        evaluation_interval = "2s"
        cooldown            = "2s"

        // check "active_connections" {
        //   source = "prometheus"
        //   query  = "nomad_client_allocs_cpu_total_percent{task='loki-${var.team}'}"

        //   strategy "target-value" {
        //     target = 70
        //   }
        // }
      }
    } # scaling

    ephemeral_disk {
      # Used to store index, cache, WAL
      # Nomad will try to preserve the disk between job updates
       size   = 500
       sticky  = true
       # migrate = true
    }

    # Canary disable, because service is too big 10 G minimum and cluster is not sized for it, so auto_promote set to false
    update {
      max_parallel      = 1
      canary            = 0
      min_healthy_time  = "10m"
      healthy_deadline  = "30m"
      progress_deadline = 0
      auto_revert       = true
      auto_promote      = false
    }

    network {
      port "server" {
        to     = 8080
      }

      port "locus" {
        to     = 8089
      }
    }

    restart {
      interval = "5m"
      attempts = 3
      delay    = "15s"
      mode     = "fail"
    }

    // volume "nabla" {
    //   type            = "csi"
    //   source          = "juicefs-gra-nabla-${var.env}"
    //   attachment_mode = "file-system"
    //   access_mode     = "multi-node-multi-writer"
    // }

    task "fastapi-sample" {
      driver = "docker"
      config {
        image = "[[ .CONTAINER_IMAGE ]]"
        ports = ["server"]

        # force_pull = true
        shm_size = 536870912 # 512MB
        auth_soft_fail = true
        # image_pull_timeout = "25m"
      }

      vault {
        policies  = ["cicd"]
      }

      template {
        data        = <<EOF
UVICORN_LOG_LEVEL=debug
OTEL_RESOURCE_ATTRIBUTES=service.name=fastapi-sample
OTEL_SERVICE_NAME=fastapi-sample
OTEL_EXPORTER_OTLP_ENDPOINT="http://otel-collector.service.gra.${var.env}.consul:4317"
PYROSCOPE_ENDPOINT="http://pyroscope.service.gra.${var.env}.consul"
EOF
        destination = "${NOMAD_SECRETS_DIR}/.env.local"

        env         = true
      }

      service {
        name = "fastapi-sample"
        port = "server"

        tags = [
          "traefik.enable=true",
          "traefik.http.routers.fastapi-sample.entrypoints=http",
          "traefik.http.routers.fastapi-sample.rule=Host(`fastapi-sample.service.gra.${var.env}.consul`)",
        ]

        check {
          name     = "server-alive"
          port     = "server"
          type     = "http"
          path     = "/health" # v1/ping /docs /metrics
          # 30s because can be heavy to lead, better to put it at this interval
          interval = "30s"
          timeout  = "5s"
        }

      } # service fastapi-sample

      resources {
        cpu    = 200 # MHz
        memory = 100 # MB
      }
    } # task fastapi-sample

    task "fastapi-sample-locus" {
      driver = "docker"
      config {
        image = "[[ .CONTAINER_IMAGE ]]"
        image_pull_timeout = "25m"
        ports = ["locus"]
        # force_pull = true

        command = "python"
        args = [
            "/code/.local/bin/locust",
            "-f",
            "nabla/perf/locustfile_jm.py",
        ]

        # shm_size = 536870912 # 512MB
      }

      // volume_mount {
      //   volume      = "nabla"
      //   destination = "/usr/share/data/"
      //   read_only   = false
      // }

      vault {
        policies  = ["cicd"]
      }

      template {
        data        = <<EOF
TEMPORALIO_HOST="temporal-app.service.gra.dev.consul"
UVICORN_LOG_LEVEL=debug
EOF
        destination = "${NOMAD_SECRETS_DIR}/.env.local"

        env         = true
      }

      service {
        # name = "fastapi-sample-locus"
        port = "locus"

        tags = [
          "traefik.enable=true",
          "traefik.http.routers.fastapi-sample-locus-${var.env}.entrypoints=http",
          "traefik.http.routers.fastapi-sample-locus-${var.env}.rule=Host(`fastapi-sample-locus.service.gra.${var.env}.consul`) || Host(`fastapi-sample-locus.${var.env}.service.gra.${var.env}.consul`)",
        ]

        # check {
        #   name     = "server-prometheus"
        #   port     = "locus"
        #   type     = "http"
        #   path     = "/metrics"
        #   interval = "5m"
        #   timeout  = "20m"
        # }

      } # service locus

      resources {
        cpu    = var.env == "dev" ? "100" : "200" # MHz
        memory = var.env == "dev" ? "400" : "500" # MB 5Gb minimum
      }
    } # task fastapi-sample-locus

    task "fastapi-sample-kong-registration" {

      driver = "docker"

      lifecycle {
        hook = "poststart"
      }

      config {
        image = "docker.io/kong/deck:v1.19.1"

        volumes = [
          "local/kong.yml:/kong.yml"
        ]

        image_pull_timeout = "10m"

        args = [
          "--kong-addr",
          "http://kong-admin.service.gra.${var.env}.consul",
          "sync",
          "--state",
          "/kong.yml",
          "--select-tag",
          "fastapi-sample"
        ]
      }

      template {
        destination = "local/kong.yml"

        data = <<EOF
_format_version: "3.0"
_info:
  select_tags:
  - fastapi-sample
services:
- connect_timeout: 60000
  host: fastapi-sample.service.gra.${var.env}.consul
  name: fastapi-sample
  path: /
  port: 80
  protocol: http
  read_timeout: 60000
  retries: 5
  routes:
  - hosts:
    %{ if var.env == "uat" }
    - fastapi-sample.staging.int.jusmundi.com
    %{ endif }
    - fastapi-sample.${var.env}.int.jusmundi.com
    https_redirect_status_code: 426
    methods:
    - GET
    - PUT
    - POST
    - DELETE
    name: fastapi-sample
    path_handling: v0
    preserve_host: false
    protocols:
    - http
    - https
    regex_priority: 0
    request_buffering: true
    response_buffering: true
    strip_path: true
  tags:
  - fastapi-sample
  write_timeout: 60000
EOF
      }

      resources {
        cpu    = 300 # Mhz
        memory = 300 # MB
      }

    } # task kong-registration

#    task "fastapi-sample-kong-disable" {
#
#      driver = "docker"
#
#      lifecycle {
#        hook = "poststop"
#      }
#
#      config {
#        image = "docker.io/kong/deck:v1.19.1"
#
#        volumes = [
#          "local/kong.yml:/kong.yml"
#        ]
#
#        image_pull_timeout = "10m"
#
#        args = [
#          "--kong-addr",
#          "http://kong-admin.service.gra.${var.env}.consul",
#          "sync",
#          "--state",
#          "/kong.yml",
#          "--select-tag",
#          "fastapi-sample"
#        ]
#      }
#
#      template {
#        destination = "local/kong.yml"
#
#        data = <<EOF
#_format_version: "3.0"
#_info:
#  select_tags:
#  - fastapi-sample
#services:
#- name: fastapi-sample
#  enabled: false
#  host: fastapi-sample.service.gra.${var.env}.consul
#EOF
#      }
#
#      resources {
#        cpu    = 300 # Mhz
#        memory = 300 # MB
#      }
#
#    } # task kong-disable

  } # group fastapi-sample

}
