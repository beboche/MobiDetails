import re
from flask import (
    Blueprint, flash, g, request, url_for, jsonify, current_app as app
)
import psycopg2
import psycopg2.extras
import json
import urllib3
import certifi
from MobiDetailsApp.db import get_db, close_db
from MobiDetailsApp import md_utilities


bp = Blueprint('api', __name__)

######################################################################
#api - variant exists?
@bp.route('/api/variant/exists/<string:variant_ghgvs>')
def api_variant_exists(variant_ghgvs=None):
	if variant_ghgvs is None:
		return jsonify({'mobidetails_error': 'No variant submitted'})
	elif re.search(r'^[Nn][Cc]_0000\d{2}\.\d{1,2}:g\..+', variant_ghgvs):#strict HGVS genomic
		db = get_db()
		match_object = re.search(r'^([Nn][Cc]_0000\d{2}\.\d{1,2}):g\.(.+)', variant_ghgvs)
		#res_common = md_utilities.get_common_chr_name(db, match_object.group(1))
		chrom, genome_version = md_utilities.get_common_chr_name(db, match_object.group(1))
		pattern = match_object.group(2)
		curs = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
		curs.execute(
			"SELECT feature_id FROM variant WHERE chr = '{0}' AND g_name LIKE '{1}%' AND genome_version = '{2}'".format(chrom, pattern, genome_version)
		)
		res = curs.fetchone()
		if res is not None:
			return jsonify(mobidetails_id = res['feature_id'])
		else:
			#return jsonify("SELECT feature_id FROM variant WHERE g_name = 'chr{0}:g.{1}' AND genome_version = '{2}'".format(chrom, pattern, genome_version))
			return jsonify(mobidetails_warning = 'The variant {} does not exist yet in MD'.format(variant_ghgvs))
	else:
		return jsonify(mobidetails_error = 'malformed query {}'.format(variant_ghgvs))
	

######################################################################
#api - variant create
@bp.route('/api/variant/create/<string:variant_chgvs>')
def api_variant_create(variant_chgvs=None):
	if variant_chgvs is None:
		return jsonify({'mobidetails_error': 'No variant submitted'})
	elif re.search(r'^[Nn][Mm]_\d+\.\d{1,2}:c\..+', variant_chgvs):#strict HGVS cdna
		db = get_db()
		match_object = re.search(r'^([Nn][Mm]_\d+)\.(\d{1,2}):c\.(.+)', variant_chgvs)
		acc_no, acc_version, new_variant = match_object.group(1), match_object.group(2), match_object.group(3)
		original_variant = new_variant
		curs = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
		curs.execute(
			"SELECT id FROM variant_feature WHERE c_name = '{0}' AND gene_name[2] = '{1}'".format(new_variant, acc_no)
		)
		res = curs.fetchone();
		if res is not None:
			return jsonify(mobidetails_id = res['id'], url = '{0}{1}'.format(request.host_url[:-1], url_for('md.variant', variant_id=res['id'])))
		else:
			#creation
			
			#get gene
			curs.execute(
				"SELECT name[1] as gene FROM gene WHERE name[2] = '{0}'".format(acc_no)
			)
			res_gene = curs.fetchone();
			if res_gene is None:
				return jsonify(mobidetails_error = 'The gene corresponding to {} is not yet present in MobiDetails'.format(acc_no))
			
					
			http = urllib3.PoolManager(cert_reqs='CERT_REQUIRED', ca_certs=certifi.where())
			vv_url = "{0}variantvalidator/GRCh38/{1}.{2}:{3}/all".format(md_utilities.urls['variant_validator_api'], acc_no, acc_version, new_variant)
			vv_key_var = "{0}.{1}:c.{2}".format(acc_no, acc_version, new_variant)		
			
			try:
				vv_data = json.loads(http.request('GET', vv_url).data.decode('utf-8'))
			except:
				close_db()
				return jsonify(mobidetails_error = 'Variant Validator did not return any value for the variant {}.'.format(new_variant))
			if re.search('[di][neu][psl]',new_variant):
				#need to redefine vv_key_var for indels as the variant name returned by vv is likely to be different form the user's
				for key in vv_data:
					if re.search('{0}.{1}'.format(acc_no, acc_version), key):
						vv_key_var = key
						#print(key)
						var_obj = re.search(r':c\.(.+)$', key)
						if var_obj is not None:
							new_variant = var_obj.group(1)
			creation_dict =  md_utilities.create_var_vv(vv_key_var, res_gene['gene'], acc_no, 'c.{}'.format(new_variant), original_variant, acc_version, vv_data, 'api', db, g)
			return jsonify(creation_dict)
	else:
		return jsonify(mobidetails_error = 'malformed query {}'.format(variant_chgvs))