#!/usr/bin/env bash

function install_rca_copilot {
    setup_develop "$RCA_COPILOT_DIR"
    if is_service_enabled horizon && [[ "$RCA_COPILOT_HORIZON_ENABLED" == "True" ]]; then
        setup_develop "$RCA_COPILOT_DIR/horizon_plugin"
    fi
}

function configure_rca_copilot {
    sudo install -d -o "$STACK_USER" -g "$STACK_USER" -m 0750 "$RCA_COPILOT_CONF_DIR" "$RCA_COPILOT_STATE_DIR"
    cp "$RCA_COPILOT_DIR/etc/rca-copilot.conf.sample" "$RCA_COPILOT_CONF"
    iniset "$RCA_COPILOT_CONF" database connection "$RCA_COPILOT_MONGO_URI"
    iniset "$RCA_COPILOT_CONF" database name "$RCA_COPILOT_MONGO_DATABASE"
    iniset "$RCA_COPILOT_CONF" api bind_host "$RCA_COPILOT_HOST"
    iniset "$RCA_COPILOT_CONF" api bind_port "$RCA_COPILOT_PORT"
    iniset "$RCA_COPILOT_CONF" api internal_service_token "$RCA_COPILOT_INTERNAL_SERVICE_TOKEN"
    iniset "$RCA_COPILOT_CONF" provider master_key "$RCA_COPILOT_PROVIDER_MASTER_KEY"
    iniset "$RCA_COPILOT_CONF" provider allowed_hosts "$RCA_COPILOT_PROVIDER_ALLOWED_HOSTS"
    iniset "$RCA_COPILOT_CONF" collector state_file "$RCA_COPILOT_STATE_DIR/collector.cursor"
    iniset "$RCA_COPILOT_CONF" parser health_file "$RCA_COPILOT_STATE_DIR/parser-worker.health"
    iniset "$RCA_COPILOT_CONF" correlation health_file "$RCA_COPILOT_STATE_DIR/correlation-worker.health"
    iniset "$RCA_COPILOT_CONF" incident health_file "$RCA_COPILOT_STATE_DIR/incident-worker.health"
    iniset "$RCA_COPILOT_CONF" enrichment health_file "$RCA_COPILOT_STATE_DIR/enrichment-worker.health"

    if is_service_enabled horizon && [[ "$RCA_COPILOT_HORIZON_ENABLED" == "True" ]]; then
        local enabled_dir="$HORIZON_DIR/openstack_dashboard/local/enabled"
        sudo install -d -o "$STACK_USER" -g "$STACK_USER" "$enabled_dir"
        for enabled_file in "$RCA_COPILOT_DIR"/horizon_plugin/rca_copilot_horizon/enabled/_*.py; do
            ln -sf "$enabled_file" "$enabled_dir/$(basename "$enabled_file")"
        done
    fi
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
}

function stop_rca_copilot {
    stop_process rca-collector
    stop_process rca-enrichment
    stop_process rca-incident
    stop_process rca-correlation
    stop_process rca-parser
    stop_process rca-api
}

function cleanup_rca_copilot {
    sudo rm -f "$HORIZON_DIR"/openstack_dashboard/local/enabled/_90{00,05,10,20,30,40,50}_rca_*.py
    sudo rm -rf "$RCA_COPILOT_CONF_DIR" "$RCA_COPILOT_STATE_DIR"
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
