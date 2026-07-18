#!/usr/bin/env bash

function configure_rca_copilot_secrets {
    local xtrace
    xtrace=$(set +o | grep xtrace)
    set +o xtrace
    sudo install -d -o "$STACK_USER" -g "$STACK_USER" -m 0750 "$RCA_COPILOT_STATE_DIR"
    if [[ -f "$RCA_COPILOT_SECRETS_FILE" ]]; then
        source "$RCA_COPILOT_SECRETS_FILE"
    else
        RCA_COPILOT_MONGO_PASSWORD=${RCA_COPILOT_MONGO_PASSWORD:-$(openssl rand -hex 24)}
        RCA_COPILOT_INTERNAL_SERVICE_TOKEN=${RCA_COPILOT_INTERNAL_SERVICE_TOKEN:-$(openssl rand -hex 32)}
        RCA_COPILOT_PROVIDER_MASTER_KEY=${RCA_COPILOT_PROVIDER_MASTER_KEY:-$(openssl rand -hex 32)}
        umask 077
        printf 'RCA_COPILOT_MONGO_PASSWORD=%q\nRCA_COPILOT_INTERNAL_SERVICE_TOKEN=%q\nRCA_COPILOT_PROVIDER_MASTER_KEY=%q\n' \
            "$RCA_COPILOT_MONGO_PASSWORD" "$RCA_COPILOT_INTERNAL_SERVICE_TOKEN" \
            "$RCA_COPILOT_PROVIDER_MASTER_KEY" > "$RCA_COPILOT_SECRETS_FILE"
    fi
    RCA_COPILOT_MONGO_URI=${RCA_COPILOT_MONGO_URI:-mongodb://$RCA_COPILOT_MONGO_USER:$RCA_COPILOT_MONGO_PASSWORD@127.0.0.1:27017/$RCA_COPILOT_MONGO_DATABASE?authSource=admin}
    $xtrace
}

function start_rca_copilot_mongodb {
    local xtrace
    xtrace=$(set +o | grep xtrace)
    set +o xtrace
    if docker inspect "$RCA_COPILOT_MONGO_CONTAINER" >/dev/null 2>&1 && \
        [[ ! -f "$RCA_COPILOT_SECRETS_FILE" ]]; then
        RCA_COPILOT_MONGO_PASSWORD=$(docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' \
            "$RCA_COPILOT_MONGO_CONTAINER" | sed -n 's/^MONGO_INITDB_ROOT_PASSWORD=//p')
    fi
    configure_rca_copilot_secrets
    if docker inspect "$RCA_COPILOT_MONGO_CONTAINER" >/dev/null 2>&1; then
        docker start "$RCA_COPILOT_MONGO_CONTAINER" >/dev/null
    else
        docker volume create rca-copilot-mongodb-data >/dev/null
        docker run -d --name "$RCA_COPILOT_MONGO_CONTAINER" \
            --restart unless-stopped \
            -e MONGO_INITDB_ROOT_USERNAME="$RCA_COPILOT_MONGO_USER" \
            -e MONGO_INITDB_ROOT_PASSWORD="$RCA_COPILOT_MONGO_PASSWORD" \
            -e MONGO_INITDB_DATABASE="$RCA_COPILOT_MONGO_DATABASE" \
            -p 127.0.0.1:27017:27017 \
            -v rca-copilot-mongodb-data:/data/db \
            "$RCA_COPILOT_MONGO_IMAGE" --auth --bind_ip_all >/dev/null
    fi
    for attempt in {1..60}; do
        if docker exec "$RCA_COPILOT_MONGO_CONTAINER" mongosh --quiet \
            --username "$RCA_COPILOT_MONGO_USER" --password "$RCA_COPILOT_MONGO_PASSWORD" \
            --authenticationDatabase admin --eval 'quit(db.adminCommand("ping").ok ? 0 : 1)' \
            >/dev/null 2>&1; then
            $xtrace
            return
        fi
        sleep 1
    done
    die $LINENO "RCA Copilot MongoDB did not become ready"
}

function install_rca_copilot {
    start_rca_copilot_mongodb
    setup_develop "$RCA_COPILOT_DIR"
    if is_service_enabled horizon && [[ "$RCA_COPILOT_HORIZON_ENABLED" == "True" ]]; then
        setup_develop "$RCA_COPILOT_DIR/horizon_plugin"
    fi
}

function configure_rca_copilot {
    local xtrace
    xtrace=$(set +o | grep xtrace)
    set +o xtrace
    configure_rca_copilot_secrets
    sudo install -d -o "$STACK_USER" -g "$STACK_USER" -m 0750 "$RCA_COPILOT_CONF_DIR" "$RCA_COPILOT_STATE_DIR"
    sudo install -o "$STACK_USER" -g "$STACK_USER" -m 0640 \
        "$RCA_COPILOT_DIR/etc/rca-copilot.conf.sample" "$RCA_COPILOT_CONF"
    iniset "$RCA_COPILOT_CONF" database connection "$RCA_COPILOT_MONGO_URI"
    iniset "$RCA_COPILOT_CONF" database name "$RCA_COPILOT_MONGO_DATABASE"
    iniset "$RCA_COPILOT_CONF" api bind_host "$RCA_COPILOT_HOST"
    iniset "$RCA_COPILOT_CONF" api bind_port "$RCA_COPILOT_PORT"
    iniset "$RCA_COPILOT_CONF" api internal_service_token "$RCA_COPILOT_INTERNAL_SERVICE_TOKEN"
    iniset "$RCA_COPILOT_CONF" api policy_file "$RCA_COPILOT_CONF_DIR/policy.yaml"
    iniset "$RCA_COPILOT_CONF" provider master_key "$RCA_COPILOT_PROVIDER_MASTER_KEY"
    iniset "$RCA_COPILOT_CONF" provider allowed_hosts "$RCA_COPILOT_PROVIDER_ALLOWED_HOSTS"
    iniset "$RCA_COPILOT_CONF" collector state_file "$RCA_COPILOT_STATE_DIR/collector.cursor"
    iniset "$RCA_COPILOT_CONF" parser health_file "$RCA_COPILOT_STATE_DIR/parser-worker.health"
    iniset "$RCA_COPILOT_CONF" correlation health_file "$RCA_COPILOT_STATE_DIR/correlation-worker.health"
    iniset "$RCA_COPILOT_CONF" incident health_file "$RCA_COPILOT_STATE_DIR/incident-worker.health"
    iniset "$RCA_COPILOT_CONF" enrichment health_file "$RCA_COPILOT_STATE_DIR/enrichment-worker.health"
    sudo install -o "$STACK_USER" -g "$STACK_USER" -m 0640 "$RCA_COPILOT_DIR/etc/policy.yaml" "$RCA_COPILOT_CONF_DIR/policy.yaml"

    if is_service_enabled horizon && [[ "$RCA_COPILOT_HORIZON_ENABLED" == "True" ]]; then
        local enabled_dir="$HORIZON_DIR/openstack_dashboard/local/enabled"
        sudo install -d -o "$STACK_USER" -g "$STACK_USER" "$enabled_dir"
        for enabled_file in "$RCA_COPILOT_DIR"/horizon_plugin/rca_copilot_horizon/enabled/_*.py; do
            ln -sf "$enabled_file" "$enabled_dir/$(basename "$enabled_file")"
        done
    fi
    $xtrace
}

function create_rca_copilot_accounts {
    if is_service_enabled key; then
        get_or_create_service "rca-copilot" "rca" "OpenStack Root Cause Analysis"
        get_or_create_endpoint "rca" "$REGION_NAME" "http://$RCA_COPILOT_HOST:$RCA_COPILOT_PORT" "http://$RCA_COPILOT_HOST:$RCA_COPILOT_PORT" "http://$RCA_COPILOT_HOST:$RCA_COPILOT_PORT"
    fi
}

function start_rca_copilot {
    run_process rca-api "$RCA_COPILOT_BIN_DIR/rca-copilot-api --config-file $RCA_COPILOT_CONF"
    run_process rca-parser "$RCA_COPILOT_BIN_DIR/rca-copilot-parser-worker --config-file $RCA_COPILOT_CONF"
    run_process rca-correlation "$RCA_COPILOT_BIN_DIR/rca-copilot-correlation-worker --config-file $RCA_COPILOT_CONF"
    run_process rca-incident "$RCA_COPILOT_BIN_DIR/rca-copilot-incident-worker --config-file $RCA_COPILOT_CONF"
    run_process rca-enrichment "$RCA_COPILOT_BIN_DIR/rca-copilot-enrichment-worker --config-file $RCA_COPILOT_CONF"
    run_process rca-collector "$RCA_COPILOT_BIN_DIR/rca-copilot-collector --config-file $RCA_COPILOT_CONF"
    for service in rca-api rca-parser rca-correlation rca-incident rca-enrichment rca-collector; do
        iniset -sudo "$SYSTEMD_DIR/devstack@$service.service" Service Restart on-failure
        iniset -sudo "$SYSTEMD_DIR/devstack@$service.service" Service RestartSec 5
    done
    $SYSTEMCTL daemon-reload
    for attempt in {1..60}; do
        if curl -fsS "http://$RCA_COPILOT_HOST:$RCA_COPILOT_PORT/health" >/dev/null && \
            $SYSTEMCTL is-active --quiet devstack@rca-parser devstack@rca-correlation \
                devstack@rca-incident devstack@rca-enrichment devstack@rca-collector; then
            return
        fi
        sleep 1
    done
    die $LINENO "RCA Copilot services did not become healthy"
}

function stop_rca_copilot {
    stop_process rca-collector
    stop_process rca-enrichment
    stop_process rca-incident
    stop_process rca-correlation
    stop_process rca-parser
    stop_process rca-api
    docker stop "$RCA_COPILOT_MONGO_CONTAINER" >/dev/null 2>&1 || true
}

function cleanup_rca_copilot {
    sudo rm -f "$HORIZON_DIR"/openstack_dashboard/local/enabled/_90{00,05,10,20,30,40,50}_rca_*.py
    sudo rm -rf "$RCA_COPILOT_CONF_DIR" "$RCA_COPILOT_STATE_DIR"
    docker rm -f "$RCA_COPILOT_MONGO_CONTAINER" >/dev/null 2>&1 || true
    docker volume rm rca-copilot-mongodb-data >/dev/null 2>&1 || true
}

if [[ "$1" == "stack" && "$2" == "pre-install" ]]; then
    :
elif [[ "$1" == "stack" && "$2" == "install" ]]; then
    install_rca_copilot
elif [[ "$1" == "stack" && "$2" == "post-config" ]]; then
    configure_rca_copilot
    create_rca_copilot_accounts
elif [[ "$1" == "stack" && "$2" == "extra" ]]; then
    start_rca_copilot
elif [[ "$1" == "unstack" ]]; then
    stop_rca_copilot
elif [[ "$1" == "clean" ]]; then
    cleanup_rca_copilot
fi
