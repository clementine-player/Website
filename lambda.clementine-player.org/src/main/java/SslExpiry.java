package org.clementineplayer.lambda;

import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.LambdaLogger;

import org.json.JSONObject;

import java.util.Date;

import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;
import javax.net.SocketFactory;
import javax.net.ssl.SSLSession;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;
import javax.security.cert.X509Certificate;

public class SslExpiry {

  private final SocketFactory socketFactory = SSLSocketFactory.getDefault();

  public String handler(String domain, Context context) throws Exception {
    LambdaLogger logger = context.getLogger();
    logger.log("received: " + domain + "\n");

    SSLSocket socket = (SSLSocket) socketFactory.createSocket(domain, 443);
    SSLSession session = socket.getSession();
    X509Certificate[] certificates = session.getPeerCertificateChain();
    socket.close();
    for (X509Certificate cert : certificates) {
      Date expires = cert.getNotAfter();
      logger.log(cert.getSubjectDN().getName() + "\n");
      logger.log(expires.toString() + "\n");

      LdapName name = new LdapName(cert.getSubjectDN().getName());
      for (Rdn rdn : name.getRdns()) {
        if (rdn.getType().equalsIgnoreCase("CN")) {
          String cn = (String) rdn.getValue();
          if (cn.equals(domain)) {
            // This is the certificate for the actual domain.
            logger.log("Found cert for domain: " + cn + "\n");
            logger.log("Expires: " + cert.getNotAfter().toString() + "\n");
            return serialize(domain, expires);
          }
        }
      }
    }
    return "{}";
  }

  private String serialize(String domain, Date expires) {
    return new JSONObject()
        .put("domain", domain)
        .put("expires", expires.toString())
        .toString();
  }
}
